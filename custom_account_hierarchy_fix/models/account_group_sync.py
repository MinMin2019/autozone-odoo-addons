# -*- coding: utf-8 -*-
"""สร้าง/ซิงก์ Account Group (กลุ่มบัญชีตามช่วงเลข) ให้เป็นชั้นตามผังแม่ sh_parent_id

ทำไมต้องมี: รายงานมาตรฐานของ Odoo (P&L / งบดุล / งบทดลอง) มีสวิตช์
"Hierarchy and Subtotals" อยู่แล้ว แต่มันจัดชั้นตาม account.group ซึ่งดูจาก
"ช่วงเลขบัญชี" ไม่ใช่ฟิลด์ Parent Account ของ sh_account_parent
โมดูลนี้จึงแปลงผังแม่ (บัญชี Type View) → account.group ให้อัตโนมัติ
Odoo จะไล่ชั้นแม่-ลูกของกลุ่มให้เองจากความยาว prefix (_adapt_parent_account_group)

ข้อจำกัดที่แปลงตรง ๆ ไม่ได้ (ตัว plan จะรายงานออกมาให้ตัดสินใจ ไม่เงียบ):
- account.group ยึดช่วงเลขล้วน ผูกข้ามเลขไม่ได้ เช่น 511005-511012 ที่ผังแม่
  ลากไปไว้ใต้ 512000 จะตกไปอยู่กลุ่ม 51 ตามเลขแทน  → รายงานเป็น "ลูกหลุด"
- หัวชั้นที่ prefix สั้นกว่า min_prefix_len (เช่น 100000 → "1") จะกิน
  บัญชีของหัวชั้นอื่นที่เป็นพี่น้องกัน (12x/13x/14x/15x) → ข้าม ไม่สร้าง
  ปล่อยให้ section ของรายงาน (สินทรัพย์/หนี้สิน/รายได้/ต้นทุน) เป็นชั้นบนสุดแทน
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

MIN_PREFIX_LEN_DEFAULT = 2


class AzAccountGroupSync(models.TransientModel):
    _name = "az.account.group.sync"
    _description = "สร้าง Account Groups จากผังแม่"

    min_prefix_len = fields.Integer(
        string="ความยาว prefix ต่ำสุด",
        default=MIN_PREFIX_LEN_DEFAULT,
        required=True,
        help="กันหัวชั้นบนสุด (เช่น 100000 → '1') ไปกินบัญชีของหัวชั้นอื่น "
        "ที่เป็นพี่น้องกัน — ปกติใช้ 2",
    )
    include_childless_views = fields.Boolean(
        string="รวมบัญชี View ที่ยังไม่มีลูก",
        default=True,
        help="เช่น 110000 Cash&Bank ที่ไม่มีลูกในผังแม่ แต่ช่วงเลข 11xxxx "
        "มีบัญชีอยู่จริง — ติ๊กไว้จะได้ชั้นเพิ่มให้เอง",
    )
    purge_others = fields.Boolean(
        string="ลบกลุ่มเดิมที่ไม่ได้มาจากผังแม่",
        default=True,
        help="กลุ่มเดิมมักเป็นช่วงเลข 6 หลักที่ซ้ำชื่อกับผังแม่ ถ้าไม่ลบจะได้ "
        "ยอดรวมย่อยซ้อนกันสองชั้นชื่อเดียวกัน",
    )
    report = fields.Text(string="ผลการตรวจ", readonly=True)

    # ------------------------------------------------------------------
    # ตัวช่วยอ่านผังแม่ (กันข้อมูลวนลูปไว้ด้วย เพราะ production ยังมี 510000
    # ที่ชี้ตัวเองอยู่ ดู scripts/fix_hierarchy_data.py)
    # ------------------------------------------------------------------
    @api.model
    def _az_child_map(self, accounts):
        children = {}
        for account in accounts:
            parent = account.sh_parent_id
            if parent and parent != account:
                children.setdefault(parent.id, []).append(account)
        return children

    @api.model
    def _az_descendants(self, view, children):
        """ลูกหลานทั้งสายของบัญชี View (กันลูป)"""
        seen = set()
        result = []
        stack = list(children.get(view.id, []))
        while stack:
            node = stack.pop()
            if node.id in seen or node == view:
                continue
            seen.add(node.id)
            result.append(node)
            stack.extend(children.get(node.id, []))
        return result

    @staticmethod
    def _az_common_prefix(codes):
        if not codes:
            return ""
        shortest = min(codes, key=len)
        for idx, char in enumerate(shortest):
            if any(code[idx] != char for code in codes):
                return shortest[:idx]
        return shortest

    @api.model
    def _az_base_prefix(self, code, min_len, descendant_codes, other_root_codes=()):
        """เลข prefix ที่ควรใช้แทนบัญชี View นี้

        ปกติ = เลขบัญชีตัดศูนย์ท้ายทิ้ง (530000 → '53', 531000 → '531')
        ถ้าสั้นกว่าที่กำหนด (300000 → '3') ยังใช้ได้ถ้าไม่มีหัวชั้นบนสุดตัวอื่น
        มาอยู่ในช่วงเลขเดียวกัน (เช่น '3' มีแต่ 300000 → กลุ่ม "ทุนและส่วนของ
        เจ้าของ" ครอบ 3xxxxx ได้หมด) แต่ '1' มีทั้ง 100000/120000/130000/...
        เป็นหัวชั้นบนสุดคนละอัน → กลุ่มจะชื่อผิดฝา ต้องข้าม
        ถ้าข้ามแล้วยังพอมีทาง ลองใช้เลขร่วมของลูกหลานแทน
        (800000 มีลูก 810000/810100 → '810' ตัดเหลือ '81')
        """
        if not code or not code.isdigit():
            return None, _("เลขบัญชีไม่ใช่ตัวเลขล้วน แปลงเป็นช่วงเลขไม่ได้")
        prefix = code.rstrip("0")
        if len(prefix) >= min_len:
            return prefix, None
        crowded = [c for c in other_root_codes if c.startswith(prefix)]
        if prefix and not crowded:
            return prefix, None
        common = self._az_common_prefix([c for c in descendant_codes if c])
        if len(common) >= min_len:
            return common[:min_len], None
        return None, _(
            "ช่วงเลข '%(prefix)s' มีหัวชั้นบนสุดตัวอื่นอยู่ด้วย (%(others)s) "
            "และลูกหลานไม่มีเลขร่วมกันพอ — ปล่อยให้ section ของรายงาน"
            "เป็นชั้นบนสุดแทน",
            prefix=prefix or code,
            others=", ".join(crowded) or "-",
        )

    # ------------------------------------------------------------------
    # สร้างแผน (dry-run) — เรียกจาก shell ได้ตรง ๆ
    # ------------------------------------------------------------------
    @api.model
    def _az_build_plan(self, min_prefix_len=MIN_PREFIX_LEN_DEFAULT,
                       include_childless_views=True, purge_others=True):
        company = self.env.company.root_id
        Account = self.env["account.account"].with_context(active_test=False)
        accounts = Account.search([])
        postable = [a for a in accounts if a.account_type != "view" and a.code]
        views = [a for a in accounts if a.account_type == "view" and a.code]
        children = self._az_child_map(accounts)

        # บัญชีลงรายการได้แต่ละตัวอยู่ใต้ View ตัวไหน (เอาตัวที่ใกล้ที่สุด = แม่โดยตรง)
        owner_view = {}
        for account in postable:
            node, seen = account.sh_parent_id, {account.id}
            while node and node.id not in seen:
                seen.add(node.id)
                if node.account_type == "view":
                    owner_view[account.id] = node
                    break
                node = node.sh_parent_id

        root_codes = [v.code for v in views
                      if not v.sh_parent_id or v.sh_parent_id == v]

        desired = {}   # prefix -> dict
        skipped = []
        for view in sorted(views, key=lambda a: a.code):
            descendants = self._az_descendants(view, children)
            leaf_codes = {d.code for d in descendants
                          if d.account_type != "view" and d.code}
            prefix, problem = self._az_base_prefix(
                view.code, min_prefix_len, leaf_codes,
                other_root_codes=[c for c in root_codes if c != view.code])
            if not prefix:
                skipped.append((view.code, view.name, problem))
                continue

            matched = [a for a in postable if a.code.startswith(prefix)]
            if not matched and not leaf_codes:
                skipped.append((view.code, view.name,
                                _("ช่วงเลข '%s' ไม่มีบัญชีอยู่เลย", prefix)))
                continue
            if not leaf_codes and not include_childless_views:
                skipped.append((view.code, view.name,
                                _("บัญชี View นี้ยังไม่มีลูกในผังแม่")))
                continue

            if prefix in desired:
                other = desired[prefix]
                skipped.append((view.code, view.name, _(
                    "ช่วงเลข '%(prefix)s' ซ้ำกับ %(other)s — ต้องแก้เลขบัญชีก่อน",
                    prefix=prefix, other=other["source_code"])))
                continue

            desired[prefix] = {
                "prefix": prefix,
                "name": view.name,
                "source_code": view.code,
                "source_id": view.id,
                "accounts": len(matched),
            }

        # เทียบผลลัพธ์กับผังแม่รายบัญชี: บัญชีแต่ละตัวจะตกอยู่ในกลุ่มที่ prefix
        # ยาวที่สุดที่ตรงกับเลขบัญชี — ตรงกับแม่ในผังหรือเปล่า
        prefixes = sorted(desired, key=len, reverse=True)
        moved, ungrouped, adopted = [], [], []
        for account in sorted(postable, key=lambda a: a.code):
            landed = next((p for p in prefixes if account.code.startswith(p)), None)
            parent_view = owner_view.get(account.id)
            if not landed:
                ungrouped.append((account.code, account.name,
                                  parent_view.code if parent_view else ""))
            elif not parent_view:
                adopted.append((account.code, account.name, landed))
            elif parent_view.id != desired[landed]["source_id"]:
                moved.append((account.code, account.name, parent_view.code,
                              landed, desired[landed]["source_code"]))

        existing = self.env["account.group"].search(
            [("company_id", "=", company.id)])
        by_prefix = {}
        for group in existing:
            if group.code_prefix_start == group.code_prefix_end:
                by_prefix.setdefault(group.code_prefix_start, group)

        to_create, to_update, keep = [], [], []
        for prefix, data in sorted(desired.items()):
            group = by_prefix.get(prefix)
            if not group:
                to_create.append(data)
            elif (group.name != data["name"]
                  or group.az_source_account_id.id != data["source_id"]):
                to_update.append(dict(data, group=group, old_name=group.name))
            else:
                keep.append(data)

        wanted_ids = {by_prefix[p].id for p in desired if p in by_prefix}
        to_delete = existing.filtered(lambda g: g.id not in wanted_ids) \
            if purge_others else self.env["account.group"]

        return {
            "company": company,
            "desired": desired,
            "create": to_create,
            "update": to_update,
            "keep": keep,
            "delete": to_delete,
            "skipped": skipped,
            "moved": moved,
            "ungrouped": ungrouped,
            "adopted": adopted,
        }

    @api.model
    def _az_format_plan(self, plan):
        lines = []
        add = lines.append
        add("บริษัท: %s" % plan["company"].display_name)
        add("")
        add("== กลุ่มที่จะสร้างใหม่ (%s) ==" % len(plan["create"]))
        for data in plan["create"]:
            add("  + %-8s %s %-38s (ช่วงเลข %s, ครอบ %s บัญชี)" % (
                data["source_code"], data["source_code"], data["name"],
                data["prefix"], data["accounts"]))
        add("")
        add("== กลุ่มเดิมที่จะอัปเดตให้ตรงผังแม่ (%s) ==" % len(plan["update"]))
        for data in plan["update"]:
            add("  ~ %-8s %s → %s %s" % (
                data["prefix"], data["old_name"], data["source_code"],
                data["name"]))
        add("")
        add("== กลุ่มเดิมที่ตรงอยู่แล้ว (%s) ==" % len(plan["keep"]))
        for data in plan["keep"]:
            add("  = %-8s %s" % (data["prefix"], data["name"]))
        add("")
        add("== กลุ่มเดิมที่จะลบทิ้ง (%s) ==" % len(plan["delete"]))
        for group in plan["delete"]:
            add("  - %s" % group.display_name)
        add("")
        add("== บัญชี View ที่แปลงเป็นกลุ่มไม่ได้ (%s) ==" % len(plan["skipped"]))
        for code, name, reason in plan["skipped"]:
            add("  ! %-8s %-36s %s" % (code, name, reason))

        add("")
        add("== บัญชีที่จะไปอยู่คนละที่กับผังแม่ (%s) ==" % len(plan["moved"]))
        for code, name, parent_code, prefix, group_source in plan["moved"]:
            add("  ! %-8s %-34s ผังแม่ใต้ %s → กลุ่ม %s (%s)" % (
                code, name, parent_code, prefix, group_source))
        add("")
        add("== บัญชีที่ไม่ตกกลุ่มไหนเลย (ไปกอง \"(No Group)\" ในรายงาน) (%s) ==" %
            len(plan["ungrouped"]))
        for code, name, parent_code in plan["ungrouped"]:
            add("  ! %-8s %-34s %s" % (
                code, name,
                "ผังแม่ใต้ %s" % parent_code if parent_code else "ไม่มีแม่ในผัง"))
        add("")
        add("== บัญชีไม่มีแม่ในผัง ที่กลุ่มรับไปดูแลให้ (%s) ==" % len(plan["adopted"]))
        for code, name, prefix in plan["adopted"]:
            add("  + %-8s %-34s → กลุ่ม %s" % (code, name, prefix))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # ลงมือจริง
    # ------------------------------------------------------------------
    @api.model
    def _az_apply_plan(self, plan):
        Group = self.env["account.group"]
        company = plan["company"]
        created = Group
        for data in plan["create"]:
            created |= Group.create({
                "name": data["name"],
                "code_prefix_start": data["prefix"],
                "code_prefix_end": data["prefix"],
                "company_id": company.id,
                "az_source_account_id": data["source_id"],
            })
        for data in plan["update"]:
            data["group"].write({
                "name": data["name"],
                "az_source_account_id": data["source_id"],
            })
        if plan["delete"]:
            plan["delete"].unlink()
        # ไล่ชั้นแม่-ลูกใหม่ทั้งชุดหลังลบของเก่าออก
        Group.search([("company_id", "=", company.id)])._adapt_parent_account_group()
        return created

    # ------------------------------------------------------------------
    # ปุ่มบนหน้าจอ
    # ------------------------------------------------------------------
    def _az_plan_from_wizard(self):
        self.ensure_one()
        if self.min_prefix_len < 1:
            raise UserError(_("ความยาว prefix ต่ำสุดต้องอย่างน้อย 1 หลัก"))
        return self._az_build_plan(
            min_prefix_len=self.min_prefix_len,
            include_childless_views=self.include_childless_views,
            purge_others=self.purge_others,
        )

    def action_preview(self):
        self.ensure_one()
        self.report = self._az_format_plan(self._az_plan_from_wizard())
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_apply(self):
        self.ensure_one()
        plan = self._az_plan_from_wizard()
        if not plan["create"] and not plan["update"] and not plan["delete"]:
            raise UserError(_("ไม่มีอะไรต้องเปลี่ยน — Account Groups ตรงกับผังแม่อยู่แล้ว"))
        self._az_apply_plan(plan)
        self.report = _("ทำรายการแล้ว:\n\n") + self._az_format_plan(
            self._az_build_plan(
                min_prefix_len=self.min_prefix_len,
                include_childless_views=self.include_childless_views,
                purge_others=self.purge_others,
            ))
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
