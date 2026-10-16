import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    _name = "product.category"
    _inherit = ["product.category", "mail.activity.mixin"]

    az_sku_code = fields.Char(
        "รหัสหมวด SKU", size=4, copy=False, index=True,
        help="ตัวเลข 4 หลัก = 4 หลักแรกของ SKU — หมวดที่ว่างไว้จะไม่ออก SKU "
             "(เช่น วัสดุตัดจ่ายทันที บริการ รอจัดหมวด)")
    az_sku_done_count = fields.Integer("มี SKU แล้ว", compute="_compute_az_sku_counts")
    az_sku_todo_count = fields.Integer("ยังไม่มี SKU", compute="_compute_az_sku_counts",
                                       help="สินค้าที่ใช้งานอยู่ ยังไม่มี SKU และไม่ได้ติ๊ก 'ไม่ออก SKU'")
    az_sku_exclude_count = fields.Integer("ติ๊กไม่ออก SKU", compute="_compute_az_sku_counts")
    az_sku_code_suggest = fields.Char("รหัสที่ว่างถัดไป", compute="_compute_az_sku_code_suggest")
    az_sku_skip = fields.Boolean(
        "ไม่ออก SKU ทั้งหมวด", tracking=True, copy=False,
        help="ตั้งใจให้หมวดนี้ไม่มี SKU (เช่น วัสดุตัดจ่ายทันที บริการ) — ระบบจะไม่เตือนให้ตั้งรหัส")
    az_sku_needs_code = fields.Boolean(
        "มีสินค้าแต่ยังไม่มีรหัส", compute="_compute_az_sku_needs_code", search="_search_az_sku_needs_code",
        help="หมวดย่อยล่างสุด ยังไม่มีรหัสหมวด SKU ไม่ได้ติ๊ก 'ไม่ออก SKU ทั้งหมวด' และมีสินค้าใช้งานอยู่")

    _sql_constraints = [
        ("az_sku_code_uniq", "unique(az_sku_code)", "รหัสหมวด SKU ซ้ำกับหมวดอื่น"),
    ]

    @api.constrains("az_sku_code")
    def _check_az_sku_code(self):
        for categ in self:
            if categ.az_sku_code and not re.fullmatch(r"\d{4}", categ.az_sku_code):
                raise ValidationError(f"รหัสหมวด SKU ต้องเป็นตัวเลข 4 หลัก ({categ.complete_name})")

    def _compute_az_sku_counts(self):
        Tmpl = self.env["product.template"].sudo()
        stats = {}
        for key, domain in [("done", [("az_sku", "!=", False)]),
                            ("exclude", [("az_sku", "=", False), ("az_sku_exclude", "=", True)]),
                            ("todo", [("az_sku", "=", False), ("az_sku_exclude", "=", False)])]:
            for categ, count in Tmpl._read_group([("categ_id", "in", self.ids)] + domain, ["categ_id"], ["__count"]):
                stats[(key, categ.id)] = count
        for categ in self:
            categ.az_sku_done_count = stats.get(("done", categ.id), 0)
            categ.az_sku_exclude_count = stats.get(("exclude", categ.id), 0)
            categ.az_sku_todo_count = stats.get(("todo", categ.id), 0)

    def _compute_az_sku_code_suggest(self):
        """Next free code following the 1+1+2 layout (group, level 2, level 3):
        siblings 3101, 3102 -> 3103; no coded sibling -> next level-2 digit under the grandparent."""
        used = set(self.sudo().search([("az_sku_code", "!=", False)]).mapped("az_sku_code"))
        for categ in self:
            categ.az_sku_code_suggest = False
            if categ.az_sku_code or not categ.parent_id:
                continue
            siblings = categ.parent_id.child_id.filtered("az_sku_code").mapped("az_sku_code")
            if siblings:
                # continue after the highest sibling with the same level-2 head (99 = reserved)
                head = sorted(siblings)[0][:2]
                last = max((int(c[2:]) for c in siblings if c[:2] == head and c[2:] != "99"), default=0)
                for n in range(last + 1, 99):
                    code = f"{head}{n:02d}"
                    if code not in used:
                        categ.az_sku_code_suggest = code
                        break
                continue
            grand = categ.parent_id.parent_id
            cousins = grand.child_id.child_id.filtered("az_sku_code").mapped("az_sku_code") if grand else []
            if cousins:
                group = sorted(cousins)[0][0]
                taken = {c[1] for c in used if c[0] == group}
                for digit in "123456789":
                    if digit not in taken:
                        categ.az_sku_code_suggest = f"{group}{digit}01"
                        break

    def _az_sku_needs_code_ids(self):
        self.env["product.template"].flush_model(["categ_id", "active"])
        self.flush_model(["az_sku_code", "az_sku_skip", "parent_id"])
        self.env.cr.execute("""
            SELECT c.id FROM product_category c
             WHERE c.az_sku_code IS NULL AND NOT COALESCE(c.az_sku_skip, false)
               AND NOT EXISTS (SELECT 1 FROM product_category k WHERE k.parent_id = c.id)
               AND EXISTS (SELECT 1 FROM product_template t WHERE t.categ_id = c.id AND t.active)
        """)
        return [r[0] for r in self.env.cr.fetchall()]

    def _compute_az_sku_needs_code(self):
        ids = set(self._az_sku_needs_code_ids())
        for categ in self:
            categ.az_sku_needs_code = categ.id in ids

    def _search_az_sku_needs_code(self, operator, value):
        ids = self._az_sku_needs_code_ids()
        positive = (operator == "=") == bool(value)
        return [("id", "in" if positive else "not in", ids)]

    def _az_sku_notify_missing_code(self):
        """Activity 'ตั้งรหัสหมวด SKU' for SKU managers (item approvers) — once per open category."""
        atype = self.env.ref("custom_product_sku.mail_activity_type_sku_code", raise_if_not_found=False)
        todo = self.filtered("az_sku_needs_code")
        if not atype or not todo:
            return
        group = self.env.ref("custom_product_sku.group_sku_manager")
        users = group.sudo().users.filtered(lambda u: u.active and not u.share and u.id != 1)
        real = users - self.env.ref("base.user_admin")
        users = real or users
        for categ in todo.sudo():
            if categ.activity_ids.filtered(lambda a: a.activity_type_id == atype):
                continue
            for user in users:
                categ.activity_schedule(
                    activity_type_id=atype.id, user_id=user.id,
                    summary="ตั้งรหัสหมวด SKU: %s" % categ.complete_name,
                    note="มีสินค้าเข้าหมวดนี้แต่หมวดยังไม่มีรหัส SKU — ตั้งรหัสที่ คลังสินค้า › การตั้งค่า › "
                         "จัดกลุ่มสินค้า › รหัสหมวด SKU หรือติ๊ก 'ไม่ออก SKU ทั้งหมวด' ถ้าหมวดนี้ไม่ต้องมี SKU")

    def _az_sku_close_code_activities(self):
        atype = self.env.ref("custom_product_sku.mail_activity_type_sku_code", raise_if_not_found=False)
        if atype:
            self.sudo().activity_ids.filtered(lambda a: a.activity_type_id == atype).action_feedback(
                feedback="ตั้งรหัสหมวด SKU / ตั้งไม่ออก SKU แล้ว")

    def write(self, vals):
        if vals.get("az_sku_code"):
            vals = dict(vals, az_sku_skip=False)
        res = super().write(vals)
        if vals.get("az_sku_code") or vals.get("az_sku_skip"):
            self._az_sku_close_code_activities()
        if vals.get("az_sku_code") and not self.env.context.get("az_sku_no_auto"):
            # products already in the category get their SKU once the category gets a code
            self.env["product.template"].search(
                [("categ_id", "in", self.ids), ("az_sku", "=", False)])._az_issue_sku_sorted()
        return res

    def action_az_sku_set_code(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "รหัสหมวด SKU",
            "res_model": "az.sku.categ.code",
            "view_mode": "form",
            "target": "new",
            "context": {"default_categ_id": self.id,
                        "default_code": self.az_sku_code or self.az_sku_code_suggest},
        }

    def action_az_sku_rules(self):
        return {
            "type": "ir.actions.act_window",
            "name": "กติกาการตั้งรหัส SKU",
            "res_model": "az.sku.rules",
            "view_mode": "form",
            "target": "new",
        }

    def action_az_sku_view_products(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.complete_name,
            "res_model": "product.template",
            "view_mode": "list,form",
            "domain": [("categ_id", "=", self.id)],
            "context": {"search_default_az_no_sku": 0},
        }
