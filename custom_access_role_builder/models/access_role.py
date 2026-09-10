import ast
import hashlib
import logging

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ชื่อโมดูลจริง ดึงอัตโนมัติ (__name__ = 'odoo.addons.<module>.models.access_role')
MODULE = __name__.split(".")[-3]

# ระดับสิทธิ์ -> (read, write, create, unlink)
LEVEL_PERMS = {
    "none":        (0, 0, 0, 0),
    "read":        (1, 0, 0, 0),
    # append-only: เพิ่ม record ใหม่ได้แต่ย้อนแก้ของเดิมไม่ได้ (ผู้ใช้กำหนดเอง —
    # เซฟรอบแรกผ่านแล้ว การเซฟซ้ำ/เปลี่ยน state จะถูกบล็อก ถือเป็นพฤติกรรมที่ตั้งใจ)
    "read_create": (1, 0, 1, 0),
    "edit":        (1, 1, 0, 0),
    "create":      (1, 1, 1, 0),
    "full":        (1, 1, 1, 1),
}

# app -> standard group ที่เรา "mirror สิทธิ์ read" มาไว้ที่ foundation ของเรา
# → หน้าจอของแอปนั้นทำงานได้ (อ่านโมเดลข้างเคียง/สนับสนุนครบ) โดย user ไม่มี group จริง
#   เมนูมาตรฐานจึงยังซ่อน + ข้อมูลถูก scope ด้วย record rule (doc-type / warehouse)
FOUNDATION_MIRROR_SOURCE = {
    "Accounting": "account.group_account_readonly",
    "Inventory": "stock.group_stock_user",
    "Sales": "sales_team.group_sale_salesman",
    "Purchase": "purchase.group_purchase_user",
    # HR — mirror แค่ "read" ของ group ระดับล่างสุดที่พอให้หน้าจอเปิดได้
    # (record rule มาตรฐานระดับพนักงานยังคุมให้เห็นเฉพาะของตัวเองตามเดิม)
    "Employees": "hr.group_hr_user",
    "Time Off": "hr_holidays.group_hr_holidays_responsible",
    "Expenses": "hr_expense.group_hr_expense_team_approver",
    "Attendances": "hr_attendance.group_hr_attendance_officer",
    "Approvals": "approvals.group_approval_user",
}

# ไอคอนของแอปบนสุดที่ generate (ชื่อ app -> "module,path"); ไม่พบ = ใช้ default ของ Odoo
APP_ICON = {
    "Accounting": "account,static/description/icon.png",
    "Customer": "account,static/description/icon.png",
    "Vendors": "account,static/description/icon.png",
    "Reporting": "account,static/description/icon.png",
    "Inventory": "stock,static/description/icon.png",
    "Sales": "sale_management,static/description/icon.png",
    "Purchase": "purchase,static/description/icon.png",
    "Contacts": "contacts,static/description/icon.png",
    "เงินกู้พนักงาน": "custom_hr_loan,static/description/icon.png",
}

# โมเดลลูก (บรรทัดเอกสาร) ที่ต้องเปิดสิทธิ์ตามพ่อ เมื่อระดับ >= แก้ไข ไม่งั้นบันทึกเอกสารไม่ได้
CHILD_MODELS = {
    "account.move": ["account.move.line"],
    "sale.order": ["sale.order.line"],
    "purchase.order": ["purchase.order.line"],
    "stock.picking": ["stock.move", "stock.move.line"],
}

# สิทธิ์ read โมเดลข้ามแอป ที่กลุ่มมาตรฐาน bundle ไว้ (สำหรับ smart button/ลิงก์ข้ามแอป)
# เช่น เซลส์ต้อง read account.move ไม่งั้นปุ่ม Invoices บน SO กดไม่ได้ / เปิด SO ไม่ได้
CROSS_APP_READ = {
    "Sales": ["account.move", "account.move.line"],
    "Purchase": ["account.move", "account.move.line"],
}

# menu hardening: ใส่ group ให้ root menu มาตรฐานที่เปิดกว้าง (base.group_user/ไม่มี group)
# → ซ่อนแอปจากพนักงาน role-based ที่ไม่มีกลุ่มจริง (gate ที่ root = ลูกทุกตัวหายตาม)
# หมายเหตุ: เป็นการเปลี่ยนระดับ global (กระทบทุก user) ปรับ/เพิ่มรายการได้ตามต้องการ
HARDENING_MENU_GROUPS = {
    "sale.sale_menu_root": "sales_team.group_sale_salesman",
    "planning.planning_menu_root": "planning.group_planning_user",
    "website.menu_website_configuration": "website.group_website_restricted_editor",
    "maintenance.menu_maintenance_title": "maintenance.group_equipment_manager",
    "spreadsheet_dashboard.spreadsheet_dashboard_menu_root": "base.group_system",
    # แอปที่ Odoo เปิดให้ internal user ทุกคน (เพิ่ม 20 ส.ค. 2026) —
    # role ไหนต้องใช้ ให้เพิ่มเมนูผ่าน catalog แทน
    "mail.menu_root_discuss": "base.group_system",
    "calendar.mail_menu_calendar": "base.group_system",
    "appointment.main_menu_appointments": "appointment.group_appointment_manager",
    "project_todo.menu_todo_todos": "base.group_system",
    "knowledge.knowledge_menu_root": "base.group_system",
    "contacts.menu_contacts": "base.group_partner_manager",
    "hr.menu_hr_root": "hr.group_hr_user",
    "hr_holidays.menu_hr_holidays_root": "hr_holidays.group_hr_holidays_user",
    "hr_expense.menu_hr_expense_root": "hr_expense.group_hr_expense_team_approver",
    "approvals.approvals_menu_root": "approvals.group_approval_user",
    "base.menu_management": "base.group_system",
    # root ของ utm เดิม gate ด้วย base.group_no_one ซึ่ง Internal User ทุกคน imply
    # → โผล่ทันทีที่ user เปิด debug mode เอง (?debug=1) — ปิดถาวรเหลือ admin
    "utm.menu_link_tracker_root": "base.group_system",
}

# กลุ่ม functional มาตรฐานที่ถ้า user ถืออยู่ จะทำให้ record rule ของเราเป็นหมัน (OR กว้างกว่า)
# หมายเหตุ: ไม่รวม group_account_readonly เพราะเราใช้เป็น "ฐาน read" โดยตั้งใจ (ไม่มี rule เขียนทับ)
CONFLICT_GROUP_XMLIDS = [
    "account.group_account_invoice",
    "account.group_account_user",
    "account.group_account_manager",
    "sale.group_sale_salesman",
    "sale.group_sale_salesman_all_leads",
    "sale.group_sale_manager",
    "purchase.group_purchase_user",
    "purchase.group_purchase_manager",
    "stock.group_stock_user",
    "stock.group_stock_manager",
]


class AccessRole(models.Model):
    _name = "access.role"
    _description = "Access Role"
    _order = "name"

    name = fields.Char(string="Role Name", required=True)
    code = fields.Char(
        string="Code (technical)",
        help="Used to name the underlying group — set once, do not change after Apply",
    )
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)

    include_foundation = fields.Boolean(
        string="Include Foundation",
        default=True,
        help="Grant read on supporting models (journal/account/tax...) to avoid form errors",
    )
    exclusive_membership = fields.Boolean(
        string="Exclusive membership (strict)",
        default=False,
        help="On Apply, strip all standard/technical groups from users, "
             "leaving only Internal User + Role Builder groups "
             "→ prevents unwanted apps (Accounting/Sales/Apps...) from appearing",
    )

    user_ids = fields.Many2many("res.users", string="Users with this role")
    line_ids = fields.One2many("access.role.line", "role_id", string="Access Lines")

    group_id = fields.Many2one("res.groups", string="Role group (generated)", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("applied", "Applied")],
        default="draft", string="Status", copy=False,
    )
    last_apply = fields.Datetime(string="Last Apply", readonly=True, copy=False)
    apply_summary = fields.Text(string="Last Apply Summary", readonly=True, copy=False)

    conflict_warning = fields.Text(
        string="⚠️ Conflict Check", compute="_compute_conflict_warning",
    )

    # ---------------------------------------------------------------- compute
    @api.depends("user_ids", "user_ids.groups_id", "line_ids")
    def _compute_conflict_warning(self):
        conflict_groups = self._get_conflict_groups()
        for role in self:
            msgs = []
            for user in role.user_ids:
                hit = user.groups_id & conflict_groups
                if hit:
                    msgs.append(
                        _("• %(user)s still has standard groups: %(groups)s → this role's record rules may have no effect")
                        % {"user": user.name, "groups": ", ".join(hit.mapped("full_name"))}
                    )
            role.conflict_warning = "\n".join(msgs) if msgs else False

    def _get_conflict_groups(self):
        groups = self.env["res.groups"]
        for xmlid in CONFLICT_GROUP_XMLIDS:
            grp = self.env.ref(xmlid, raise_if_not_found=False)
            if grp:
                groups |= grp
        return groups

    # ------------------------------------------------------------------- apply
    def action_apply(self):
        self.ensure_one()
        if not self.line_ids.filtered(lambda l: l.level != "none"):
            raise UserError(_("No access selected — add at least one line that is not 'No access'"))

        role_group = self._get_or_create_role_group()

        implied = self.env["res.groups"]
        counts = {"brick": 0, "access": 0, "rule": 0}

        for line in self.line_ids.filtered(lambda l: l.level != "none"):
            if not line.model_id:
                raise UserError(
                    _("Line '%s' has no model — check the catalog first") % line.catalog_id.display_name
                )
            brick = self._sync_brick(line, counts)
            implied |= brick

        # Foundation (base + mirror สิทธิ์ read ของแอปที่ role นี้แตะ)
        apps = set(self.line_ids.filtered(lambda l: l.level != "none").mapped("app"))
        if self.include_foundation:
            foundation = self.env.ref(
                "%s.group_arb_foundation" % MODULE, raise_if_not_found=False
            )
            if foundation:
                implied |= foundation

            # mirror read ของ standard group ต่อแอป (Accounting/Inventory/Sales/Purchase)
            for app in apps:
                if app in FOUNDATION_MIRROR_SOURCE:
                    implied |= self._get_or_create_app_foundation(app)

            # cross-app read (smart button/ลิงก์ข้ามแอป) เช่น Sales -> read account.move
            for app in apps:
                cross_models = CROSS_APP_READ.get(app)
                if cross_models:
                    implied |= self._get_cross_app_foundation(app, cross_models)

        # ผูกอิฐเข้า role (แทนที่ของเดิมทั้งหมด = sync)
        role_group.write({"implied_ids": [(6, 0, implied.ids)]})

        # มอบตำแหน่งให้คน (sync membership ของ group นี้ให้ตรง user_ids)
        role_group.write({"users": [(6, 0, self.user_ids.ids)]})

        # strict: ถอดกลุ่มมาตรฐาน/technical ออก เหลือแค่ Internal User + กลุ่มของเรา
        if self.exclusive_membership:
            self._enforce_exclusive_membership(role_group)

        self.state = "applied"
        self.last_apply = fields.Datetime.now()

        # สร้างเมนูใหม่ "ทั้งหมด" ด้วย shared node_cache → กัน node ซ้ำข้าม role เด็ดขาด
        # (แทนที่จะ generate เฉพาะ role นี้ ซึ่งพึ่ง DB search ที่ flaky)
        menu_count = self._rebuild_menus_all()
        summary = _(
            "Created/synced successfully\n"
            "  • Role group: %(role)s\n"
            "  • Bricks: %(brick)s\n"
            "  • ir.model.access: %(access)s\n"
            "  • ir.rule: %(rule)s\n"
            "  • Menus (whitelist): %(menus)s\n"
            "  • Users assigned: %(users)s"
        ) % {
            "role": role_group.name, "brick": counts["brick"],
            "access": counts["access"], "rule": counts["rule"],
            "menus": menu_count, "users": len(self.user_ids),
        }
        if self.conflict_warning:
            summary += _("\n\n⚠️ Conflicts found (handle manually):\n%s") % self.conflict_warning
        self.apply_summary = summary

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Apply succeeded"),
                "message": summary,
                "type": "warning" if self.conflict_warning else "success",
                "sticky": bool(self.conflict_warning),
                # reload view ปัจจุบัน → statusbar/badge เปลี่ยนเป็น Applied ทันที ไม่ต้อง refresh
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_apply_all(self):
        for role in self:
            role.action_apply()
        return True

    def action_open_add_lines(self):
        """เปิด wizard เลือก catalog หลายรายการเข้า role ทีเดียว"""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Add Multiple Lines"),
            "res_model": "access.role.line.add",
            "view_mode": "form",
            "target": "new",
            "context": {"default_role_id": self.id},
        }

    # -------------------------------------------------------------- generators
    def _role_code(self):
        self.ensure_one()
        return self.code or ("role_%s" % self.id)

    def _get_or_create_role_group(self):
        self.ensure_one()
        if self.group_id:
            self.group_id.name = self.name
            return self.group_id
        category = self.env.ref("%s.module_category_arb_roles" % MODULE)
        key = "role|%s" % self._role_code()
        group = self.env["res.groups"].search([("arb_key", "=", key)], limit=1)
        if not group:
            group = self.env["res.groups"].create({
                "name": self.name,
                "category_id": category.id,
                "arb_generated": True,
                "arb_kind": "role",
                "arb_key": key,
            })
        self.group_id = group
        return group

    def _sync_brick(self, line, counts):
        """หา/สร้างอิฐ (dedup ด้วย key = model+level+domain) พร้อม access + rule"""
        model = line.model_id
        level = line.level
        domain = (line.domain or "").strip()
        key = "brick|%s|%s|%s" % (model.model, level, domain)

        Groups = self.env["res.groups"]
        brick = Groups.search([("arb_key", "=", key)], limit=1)
        if not brick:
            # ชื่อต้อง unique ต่อ category → ต่อ domain-hash เมื่อมี rule (กันชื่อชน)
            suffix = ""
            if domain:
                suffix = " · " + hashlib.md5(domain.encode("utf-8")).hexdigest()[:6]
            category = self.env.ref("%s.module_category_arb_caps" % MODULE)
            brick = Groups.create({
                "name": "[BRICK] %s · %s%s" % (model.model, level, suffix),
                "category_id": category.id,
                "arb_generated": True,
                "arb_kind": "brick",
                "arb_key": key,
            })
            counts["brick"] += 1

        self._sync_access(brick, model, level, counts)
        if domain:
            self._sync_rule(brick, model, domain, counts)

        # เปิดสิทธิ์โมเดลลูก (บรรทัดเอกสาร) เมื่อระดับเขียน/สร้างได้ ไม่งั้นบันทึกไม่ได้
        # (read_create ส่งต่อระดับเดียวกันลงลูก → บรรทัดเอกสารก็ append-only เช่นกัน)
        if level in ("read_create", "edit", "create", "full"):
            for child_name in CHILD_MODELS.get(model.model, []):
                cm = self.env["ir.model"].search([("model", "=", child_name)], limit=1)
                if cm:
                    self._sync_access(brick, cm, level, counts)

        # companion read models (ประกาศไว้ในแคตตาล็อก) — กัน AccessError ข้ามโมเดล
        for extra in line.catalog_id.extra_read_model_ids:
            self._sync_access(brick, extra, "read", counts)

        return brick

    def _sync_access(self, brick, model, level, counts):
        r, w, c, u = LEVEL_PERMS[level]
        key = "access|%s|%s" % (brick.arb_key, model.model)
        Access = self.env["ir.model.access"]
        rec = Access.search([("arb_key", "=", key)], limit=1)
        vals = {
            "name": "arb_%s_%s" % (model.model.replace(".", "_"), level),
            "model_id": model.id,
            "group_id": brick.id,
            "perm_read": r, "perm_write": w, "perm_create": c, "perm_unlink": u,
            "arb_generated": True, "arb_key": key,
        }
        if rec:
            rec.write(vals)
        else:
            Access.create(vals)
            counts["access"] += 1

    def _sync_rule(self, brick, model, domain, counts):
        key = "rule|%s|%s" % (brick.arb_key, model.model)
        Rule = self.env["ir.rule"]
        rec = Rule.search([("arb_key", "=", key)], limit=1)
        # perm_read ต้องเป็น False: domain ของอิฐมีไว้จำกัดการ "สร้าง/แก้/ลบ" เท่านั้น
        # ถ้าบังคับตอนอ่านด้วย โมเดลที่ inherits กัน (เช่น res.users←res.partner)
        # จะโดน rule ลามจนอ่าน record ตัวเองไม่ได้ → 403 ตั้งแต่ login
        vals = {
            "name": "arb rule %s" % model.model,
            "model_id": model.id,
            "domain_force": domain,
            "groups": [(6, 0, [brick.id])],
            "perm_read": False, "perm_write": True,
            "perm_create": True, "perm_unlink": True,
            "arb_generated": True, "arb_key": key,
        }
        if rec:
            rec.write(vals)
        else:
            Rule.create(vals)
            counts["rule"] += 1

    # -------------------------------------------------------- app foundation (mirror)
    def _get_or_create_app_foundation(self, app):
        """get_or_create foundation group ต่อแอป + mirror สิทธิ์ read ของ standard group
        → หน้าจอแอปนั้นอ่านโมเดลสนับสนุนได้ครบ (ไม่ AccessError) แต่ user ไม่มี group จริง
          เมนูมาตรฐานจึงยังซ่อน + ข้อมูลถูก scope ด้วย record rule"""
        source_xmlid = FOUNDATION_MIRROR_SOURCE.get(app)
        if not source_xmlid:
            return self.env["res.groups"]
        source = self.env.ref(source_xmlid, raise_if_not_found=False)
        if not source:
            return self.env["res.groups"]

        Groups = self.env["res.groups"]
        key = "foundation|appmirror|%s" % app
        grp = Groups.search([("arb_key", "=", key)], limit=1)
        if not grp:
            category = self.env.ref("%s.module_category_arb_caps" % MODULE)
            grp = Groups.create({
                "name": "[FOUNDATION] %s read (mirror)" % app,
                "category_id": category.id,
                "arb_generated": True, "arb_kind": "foundation", "arb_key": key,
            })

        # mirror read access lines ของ source group (เฉพาะ direct — base.group_user user มีอยู่แล้ว)
        Access = self.env["ir.model.access"]
        src = Access.search([
            ("group_id", "=", source.id), ("perm_read", "=", True),
        ])
        seen = set()
        for a in src:
            if a.model_id.id in seen:
                continue
            seen.add(a.model_id.id)
            akey = "foundation|appmirror|%s|%s" % (app, a.model_id.model)
            vals = {
                "name": "arb_appmirror_%s_%s" % (app, a.model_id.model.replace(".", "_")),
                "model_id": a.model_id.id, "group_id": grp.id,
                "perm_read": 1, "perm_write": 0, "perm_create": 0, "perm_unlink": 0,
                "arb_generated": True, "arb_key": akey,
            }
            rec = Access.search([("arb_key", "=", akey)], limit=1)
            if rec:
                rec.write(vals)
            else:
                Access.create(vals)
        return grp

    def _get_cross_app_foundation(self, app, model_names):
        """get_or_create foundation group ที่เปิด read โมเดลข้ามแอป (สำหรับ smart button)"""
        Groups = self.env["res.groups"]
        key = "foundation|crossread|%s" % app
        grp = Groups.search([("arb_key", "=", key)], limit=1)
        if not grp:
            category = self.env.ref("%s.module_category_arb_caps" % MODULE)
            grp = Groups.create({
                "name": "[FOUNDATION] %s cross-app read" % app,
                "category_id": category.id,
                "arb_generated": True, "arb_kind": "foundation", "arb_key": key,
            })
        Access = self.env["ir.model.access"]
        for mn in model_names:
            m = self.env["ir.model"].search([("model", "=", mn)], limit=1)
            if not m:
                continue
            akey = "foundation|crossread|%s|%s" % (app, mn)
            vals = {
                "name": "arb_crossread_%s_%s" % (app, mn.replace(".", "_")),
                "model_id": m.id, "group_id": grp.id,
                "perm_read": 1, "perm_write": 0, "perm_create": 0, "perm_unlink": 0,
                "arb_generated": True, "arb_key": akey,
            }
            rec = Access.search([("arb_key", "=", akey)], limit=1)
            if rec:
                rec.write(vals)
            else:
                Access.create(vals)
        return grp

    def _enforce_exclusive_membership(self, role_group):
        """ถอดกลุ่มที่ไม่ใช่ของ Role Builder ออกจาก user เหลือ Internal User + กลุ่มของเรา"""
        base_user = self.env.ref("base.group_user")
        for user in self.user_ids:
            if user.id == SUPERUSER_ID:
                continue  # ห้ามถอดสิทธิ์ superuser เด็ดขาด
            keep = user.groups_id.filtered(lambda g: g.arb_generated) | base_user | role_group
            user.write({"groups_id": [(6, 0, keep.ids)]})

    # --------------------------------------------------------------- menu builder
    def _derive_context(self, domain_str):
        """แปลง domain -> context default ให้ปุ่มสร้างตั้งค่าถูก เช่น
        [('move_type','=','in_invoice')] -> {'default_move_type':'in_invoice'}"""
        try:
            dom = ast.literal_eval(domain_str)
        except Exception:  # noqa: BLE001
            return "{}"
        ctx = {}
        for cond in dom:
            if isinstance(cond, (list, tuple)) and len(cond) == 3 and cond[1] == "=":
                field, val = cond[0], cond[2]
                if isinstance(val, (bool, int, str)):
                    ctx["default_%s" % field] = val
        return repr(ctx) if ctx else "{}"

    def _menu_model(self):
        """ir.ui.menu แบบเห็น 'ทุก' record — search() ปกติของ ir.ui.menu กรองเมนูที่
        user มองไม่เห็นออก (node ที่ไม่มี action และไม่มีลูก = มองไม่เห็น) ทำให้
        delete/dedup หา record ไม่เจอ → root กำพร้าโผล่ซ้ำทุกรอบ revoke→apply
        ต้อง search ผ่าน context ir.ui.menu.full_list เสมอ"""
        return self.env["ir.ui.menu"].with_context(**{"ir.ui.menu.full_list": True})

    def _get_shared_node(self, parts, node_cache):
        """get/create เมนู node ที่ 'shared ข้าม role' ตาม path
        ตัวแรก = แอปบนสุด (parent=False + web_icon), ที่เหลือซ้อนลงไป
        dedup ด้วย (ชื่อ + parent) — robust กว่า arb_key + cache ใน call เดียวกัน"""
        Menu = self._menu_model()
        seq_map = self._std_seq_map(node_cache)
        parent = self.env["ir.ui.menu"]
        acc = ()
        for i, part in enumerate(parts):
            acc = acc + (part,)
            if acc in node_cache:
                parent = node_cache[acc]
                continue
            pid = parent.id if parent else False
            node = Menu.search([
                ("name", "=", part), ("arb_generated", "=", True),
                ("parent_id", "=", pid),
            ], limit=1)
            if not node:
                vals = {
                    "name": part, "parent_id": pid,
                    "arb_generated": True, "arb_key": "menu|node|%s" % part,
                    # เรียงตามเมนูมาตรฐาน Odoo ถ้า path นี้มีของจริงอยู่
                    "sequence": seq_map.get(acc, 10),
                }
                if i == 0 and part in APP_ICON:
                    vals["web_icon"] = APP_ICON[part]
                node = Menu.create(vals)
            node_cache[acc] = node
            parent = node
        return parent

    def _std_seq_map(self, node_cache):
        """map path(tuple ชื่อเมนูจาก root) -> sequence ของเมนูมาตรฐาน Odoo
        → whitelist เรียงลำดับเหมือนเมนูจริงทุกชั้น (cache ใน node_cache ต่อรอบ build)"""
        seq_map = node_cache.get("__seq_map__")
        if seq_map is not None:
            return seq_map
        menus = self._menu_model().search([("arb_generated", "=", False)])
        info = {m.id: (m.name, m.parent_id.id, m.sequence) for m in menus}
        seq_map = {}
        for m in menus:
            path, cur, ok = [], m.id, True
            while cur:
                if cur not in info:
                    ok = False
                    break
                name, parent_id, _s = info[cur]
                path.append(name)
                cur = parent_id
            if ok:
                seq_map[tuple(reversed(path))] = m.sequence
        node_cache["__seq_map__"] = seq_map
        return seq_map

    def _generate_menus(self, node_cache=None):
        """สร้างเมนู whitelist: แอปบนสุดต่อ App (shared ข้าม role), leaf gate ด้วย role group
        ลบ leaf/action ของ role นี้แล้วสร้างใหม่ (node ที่ shared ไม่แตะ)
        node_cache: dict ใช้ร่วมกันข้าม role (จาก Rebuild) กัน node ซ้ำแบบเด็ดขาด"""
        self.ensure_one()
        if node_cache is None:
            node_cache = {}
        Menu = self._menu_model()
        Act = self.env["ir.actions.act_window"]

        lines = self.line_ids.filtered(lambda l: l.level != "none" and l.model_id)
        if not lines or not self.group_id:
            return 0

        gid = self.group_id.id
        seq = 10
        count = 0
        for line in lines:
            cat = line.catalog_id
            # โครงเมนูซ้อน: node บนสุด = ชื่อ App สะอาดเสมอ (ทุก entry ของ app เดียวกัน = node เดียว)
            app_name = (line.app or "").strip() or "Other"
            if cat.menu_path:
                raw = [p.strip() for p in cat.menu_path.split("/") if p.strip()]
                # ตัด segment แรกที่ซ้ำกับชื่อ app (กันชื่อ root menu ต่างจาก App นิดหน่อย)
                if raw and raw[0].lower() == app_name.lower():
                    raw = raw[1:]
                parts = [app_name] + raw
            else:
                sec = (cat.section or "").strip()
                # หมวดชื่อซ้ำกับแอป (เช่น Accounting > Accounting) ต้องคงไว้ —
                # เมนูมาตรฐาน Odoo ก็ซ้อนแบบนี้ ถ้าข้ามจะกลายเป็น leaf กองที่แถบบน
                parts = [app_name] + ([sec] if sec else [])

            parent = self._get_shared_node(parts, node_cache)

            # leaf shared ข้าม role: catalog เดียวกัน + domain เดียวกัน = เมนูเดียว
            # gate ด้วยหลาย group (user ถือหลาย role จะไม่เห็นเมนูซ้ำ)
            domain = (line.domain or cat.domain or "").strip() or "[]"
            leaf_key = ("__leaf__", parent.id, cat.id, domain)
            existing_leaf = node_cache.get(leaf_key)
            if existing_leaf:
                existing_leaf.write({"groups_id": [(4, gid)]})
                count += 1
                continue

            if cat.client_action_id:
                # รายงาน/หน้าจอที่เป็น client action (เช่น account report ของ Enterprise)
                action_ref = "ir.actions.client,%s" % cat.client_action_id.id
            elif cat.action_id:
                # ใช้ action เดิมของ custom module (context/view/default ครบ)
                action_ref = "ir.actions.act_window,%s" % cat.action_id.id
            else:
                act = Act.create({
                    "name": cat.name,
                    "res_model": line.model_id.model,
                    "view_mode": (cat.view_mode or "list,form").strip(),
                    "domain": domain,
                    "context": self._derive_context(domain),
                    "arb_generated": True, "arb_key": "act|shared|%s" % cat.id,
                })
                action_ref = "ir.actions.act_window,%s" % act.id
            # เรียงตามเมนูจริงของ Odoo; entry ที่ไม่มีเมนูจริง (เช่นจาก CSV ล้วน)
            # ตกไปท้ายหมวดด้วยเลขวิ่ง 500+ (เลขมาตรฐานอยู่ช่วง 0-200)
            std_seq = self._std_seq_map(node_cache).get(tuple(parts) + (cat.name,))
            leaf = Menu.create({
                "name": cat.name,
                "parent_id": parent.id,
                "action": action_ref,
                "groups_id": [(6, 0, [gid])],
                "arb_generated": True, "arb_key": "menu|shared|leaf|%s" % cat.id,
                "sequence": std_seq if std_seq is not None else 500 + seq,
            })
            node_cache[leaf_key] = leaf
            seq += 1
            count += 1
        return count

    # -------------------------------------------------------------- housekeeping
    def action_unlink_generated(self):
        """ถอนสิทธิ์ + เมนูที่ generate ของ role นี้ (อิฐที่ยังมีคนใช้จะไม่ลบ)"""
        for role in self:
            if role.group_id:
                role.group_id.unlink()
                role.group_id = False
            role.state = "draft"
            role.last_apply = False
            role.apply_summary = False
        # rebuild ทั้งกระดาน (ลบ generated ทั้งหมดแล้วสร้างใหม่จาก role ที่ยัง applied)
        # → เมนู/action ของ role นี้หายเกลี้ยง รวมถึง app root ที่ไม่มีลูกแล้ว ไม่เหลือไอคอนกำพร้า
        self._rebuild_menus_all()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Access revoked"),
                "message": _("Generated group/menus removed — role back to draft"),
                "type": "success", "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def unlink(self):
        """ลบ role → ล้าง group/เมนู/action ที่ generate ด้วย (กัน orphan)"""
        self.action_unlink_generated()
        return super().unlink()

    @api.model
    def _rebuild_menus_all(self):
        """ลบเมนู/action ที่ generate ทั้งหมด แล้วสร้างใหม่จาก role ที่ applied
        ใช้ shared node_cache (dict) → node เดียวต่อ path เด็ดขาด ไม่พึ่ง DB search"""
        self._menu_model().search([("arb_generated", "=", True)]).unlink()
        self.env["ir.actions.act_window"].search([("arb_generated", "=", True)]).unlink()
        node_cache = {}
        total = 0
        for role in self.env["access.role"].search([("state", "=", "applied")]):
            total += role._generate_menus(node_cache)
        return total

    @api.model
    def action_rebuild_all_menus(self):
        """hard reset (ปุ่ม): ล้าง + สร้างเมนูใหม่ทั้งหมด"""
        total = self._rebuild_menus_all()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Rebuild All Menus"),
                "message": _("Rebuilt %s menu item(s) across all applied roles") % total,
                "type": "success", "sticky": False,
            },
        }

    @api.model
    def action_apply_menu_hardening(self):
        """gate root menu มาตรฐานที่เปิดกว้าง → ซ่อนแอปข้อมูล/เครื่องมือจากพนักงาน role-based
        (global; ข้ามรายการที่ไม่พบ ไม่ error)"""
        done, skipped = [], []
        for menu_xmlid, group_xmlid in HARDENING_MENU_GROUPS.items():
            menu = self.env.ref(menu_xmlid, raise_if_not_found=False)
            group = self.env.ref(group_xmlid, raise_if_not_found=False)
            if menu and group:
                menu.write({"groups_id": [(6, 0, [group.id])]})
                done.append(menu_xmlid)
            else:
                skipped.append(menu_xmlid)
        msg = _("Menus gated: %s") % len(done)
        if skipped:
            msg += _("\nSkipped (menu/group not found): %s") % ", ".join(skipped)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Harden Standard Menus"),
                "message": msg, "type": "success", "sticky": True,
            },
        }

    @api.model
    def action_reset_default_user_template(self):
        """ล้าง template `base.default_user` (ต้นแบบสิทธิ์ตอนสร้าง user ใหม่) ให้เหลือ
        Internal User อย่างเดียว — กัน user ใหม่เกิดมาพร้อมสิทธิ์ Administrator ทุกแอป
        (เคสจริง 20 ส.ค. 2026: template ถูกบันทึกไว้ ~80 กลุ่ม) สิทธิ์จริงให้มอบผ่าน role"""
        tmpl = self.env.ref("base.default_user", raise_if_not_found=False)
        if not tmpl:
            raise UserError(_("base.default_user template not found"))
        base_user = self.env.ref("base.group_user")
        before = len(tmpl.groups_id)
        tmpl.write({"groups_id": [(6, 0, base_user.ids)]})
        # implied ของ Internal User จะถูกเติมกลับอัตโนมัติ — นับหลัง write เพื่อรายงานตามจริง
        after = len(tmpl.groups_id)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Reset Default User Template"),
                "message": _(
                    "base.default_user: %(before)s groups → %(after)s groups "
                    "(Internal User + implied). New users now start clean; "
                    "grant access via roles."
                ) % {"before": before, "after": after},
                "type": "success", "sticky": True,
            },
        }

    @api.model
    def action_cleanup_orphans(self):
        """เก็บกวาด group/เมนู/action ที่ generate แต่ role ต้นทางถูกลบไปแล้ว"""
        valid_codes = {r._role_code() for r in self.search([])}
        Groups = self.env["res.groups"]
        Menu = self._menu_model()
        Act = self.env["ir.actions.act_window"]

        def _code_of(key, prefix):
            parts = (key or "").split("|")
            return parts[1] if len(parts) >= 2 and parts[0] == prefix else None

        dead_groups = Groups.browse()
        for g in Groups.search([("arb_kind", "=", "role")]):
            code = _code_of(g.arb_key, "role")
            if code and code not in valid_codes:
                dead_groups |= g

        dead_menus = Menu.browse()
        for m in Menu.search([("arb_generated", "=", True)]):
            code = _code_of(m.arb_key, "menu")
            # "menu|node|..." / "menu|shared|..." = ไม่ผูก role -> ข้าม (Rebuild จัดการเอง)
            if code and code not in ("node", "shared") and code not in valid_codes:
                dead_menus |= m

        dead_acts = Act.browse()
        for a in Act.search([("arb_generated", "=", True)]):
            code = _code_of(a.arb_key, "act")
            if code and code != "shared" and code not in valid_codes:
                dead_acts |= a

        n = len(dead_groups) + len(dead_menus) + len(dead_acts)
        dead_menus.unlink()
        dead_acts.unlink()
        dead_groups.unlink()

        # prune shared node ที่ว่าง (ไม่มีเมนูลูก) — วนจนไม่มีเปลี่ยน (ลบลูกในสุดก่อน)
        pruned = True
        while pruned:
            pruned = False
            for node in Menu.search([("arb_key", "=like", "menu|node|%")]):
                if not node.child_id and not node.action:
                    node.unlink()
                    n += 1
                    pruned = True
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Unused groups removed"),
                "message": _("Removed groups/menus/actions/empty nodes: %s") % n,
                "type": "success", "sticky": False,
            },
        }


class AccessRoleLine(models.Model):
    _name = "access.role.line"
    _description = "Access Role Line"
    _order = "app, catalog_id"

    role_id = fields.Many2one("access.role", required=True, ondelete="cascade")
    catalog_id = fields.Many2one("access.catalog", string="Menu / Document", required=True)

    app = fields.Char(related="catalog_id.app", store=True, string="App")
    model_id = fields.Many2one(related="catalog_id.model_id", store=True, string="Data Model")
    needs_rule = fields.Boolean(related="catalog_id.needs_rule", string="Needs rule")

    level = fields.Selection(
        selection="_level_selection", string="Access Level", required=True, default="read",
    )
    domain = fields.Char(
        string="Domain (override)",
        help="Normally taken from the catalog; edit only to override",
    )

    @api.model
    def _level_selection(self):
        return [
            ("none", "— No access"),
            ("read", "R · Read only"),
            ("read_create", "RC · Read + Create (no edit, append-only)"),
            ("edit", "E · Read + Edit"),
            ("create", "C · Read + Edit + Create"),
            ("full", "F · Full (can delete)"),
        ]

    @api.onchange("catalog_id")
    def _onchange_catalog_id(self):
        for line in self:
            if line.catalog_id:
                line.domain = line.catalog_id.domain
                if line.catalog_id.default_level:
                    line.level = line.catalog_id.default_level

    _sql_constraints = [
        ("uniq_role_catalog", "unique(role_id, catalog_id)",
         "This menu is already added to this role"),
    ]
