from odoo import api, fields, models
from odoo.exceptions import UserError

# first digit of a category code = top-level group (same numbering as the stock account groups)
GROUP_DIGITS = {"1": "สีและเคมีภัณฑ์", "2": "วัสดุสิ้นเปลืองโรงงาน", "3": "วัสดุสิ้นเปลืองทั่วไป", "6": "อะไหล่รถยนต์"}


class AzSkuCategCode(models.TransientModel):
    """Set / change / clear a category's SKU code without giving write access to categories
    (categories also carry the stock/expense accounts)."""
    _name = "az.sku.categ.code"
    _description = "ตั้งรหัสหมวด SKU"

    categ_id = fields.Many2one("product.category", "หมวด", required=True, readonly=True)
    # computed from the saved category (not related): in the web form the category arrives as a
    # draft copy whose fields are not reliable, so everything is read back from the database
    current_code = fields.Char("รหัสปัจจุบัน", compute="_compute_categ_info")
    suggest = fields.Char("รหัสที่ว่างถัดไป", compute="_compute_categ_info")
    code = fields.Char("รหัสใหม่ (4 หลัก)", size=4, help="ว่าง = หมวดนี้ไม่ออก SKU ให้สินค้าใหม่")
    skip = fields.Boolean("หมวดนี้ไม่ออก SKU (ตั้งใจ)",
                          default=lambda self: self.env["product.category"].browse(
                              self.env.context.get("default_categ_id")).az_sku_skip,
                          help="ติ๊กเมื่อหมวดนี้ไม่ต้องมี SKU — ระบบจะไม่เตือนให้ตั้งรหัสอีก")
    todo_count = fields.Integer("สินค้าที่จะได้ SKU", compute="_compute_categ_info")
    done_count = fields.Integer("มี SKU แล้ว", compute="_compute_categ_info")
    sibling_info = fields.Text("หมวดข้างเคียงที่มีรหัสแล้ว", compute="_compute_sibling_info")
    code_warning = fields.Char(compute="_compute_code_warning")

    def _categ(self):
        """The saved category behind the wizard (never the form's draft copy)."""
        self.ensure_one()
        return self.env["product.category"].sudo().browse(self.categ_id._origin.id or self.categ_id.id)

    def _siblings(self):
        categ = self._categ()
        if not categ.parent_id:
            return self.env["product.category"]
        return self.env["product.category"].sudo().search(
            [("parent_id", "=", categ.parent_id.id), ("id", "!=", categ.id), ("az_sku_code", "!=", False)],
            order="az_sku_code")

    @api.depends("categ_id")
    def _compute_categ_info(self):
        for wiz in self:
            categ = wiz._categ() if wiz.categ_id else self.env["product.category"]
            wiz.current_code = categ.az_sku_code
            wiz.suggest = categ.az_sku_code_suggest
            wiz.todo_count = categ.az_sku_todo_count
            wiz.done_count = categ.az_sku_done_count

    @api.depends("categ_id")
    def _compute_sibling_info(self):
        for wiz in self:
            sibs = wiz._siblings() if wiz.categ_id else []
            wiz.sibling_info = "\n".join(f"{c.az_sku_code}  {c.name}" for c in sibs) or \
                "(ยังไม่มีหมวดในระดับเดียวกันที่มีรหัส — ดูกติกาหลัก 1-2 ด้านล่าง)"

    @api.depends("code", "categ_id")
    def _compute_code_warning(self):
        used = dict(self.env["product.category"].sudo().search([("az_sku_code", "!=", False)])
                    .mapped(lambda c: (c.az_sku_code, c.complete_name)))
        for wiz in self:
            code = (wiz.code or "").strip()
            msg = []
            if code:
                if len(code) != 4 or not code.isdigit():
                    msg.append("รหัสต้องเป็นตัวเลข 4 หลัก")
                else:
                    if code[0] not in GROUP_DIGITS:
                        msg.append(f"หลักแรก {code[0]} ไม่ใช่กลุ่มที่ออก SKU (1/2/3/6)")
                    sibs = wiz._siblings()
                    heads = {c.az_sku_code[:2] for c in sibs if c.az_sku_code}
                    if heads and code[:2] not in heads:
                        msg.append("2 หลักแรกไม่ตรงกับหมวดข้างเคียง (%s) — ตรวจอีกครั้ง"
                                   % ", ".join(h + "xx" for h in sorted(heads)))
                    if code[2:] == "00":
                        msg.append("หลัก 3-4 ต้องเป็น 01-99 (00 ไม่ใช้)")
                    if code in used and used[code] != wiz._categ().complete_name:
                        msg.append(f"รหัสนี้ใช้แล้วกับ {used[code]}")
            wiz.code_warning = " / ".join(msg) or False

    @api.onchange("code")
    def _onchange_code(self):
        if self.code:
            self.code = self.code.strip()

    def action_confirm(self):
        self.ensure_one()
        if not self.env.user.has_group("custom_product_sku.group_sku_manager"):
            raise UserError("เฉพาะผู้ดูแลรหัสสินค้า (SKU) เท่านั้น")
        code = (self.code or "").strip() or False
        categ = self._categ()
        skip = bool(self.skip and not code)
        if code == categ.az_sku_code and skip == categ.az_sku_skip:
            return {"type": "ir.actions.act_window_close"}
        old = categ.az_sku_code
        categ.write({"az_sku_code": code, "az_sku_skip": skip})
        categ.message_post(body=f"รหัสหมวด SKU {old or '-'} → {code or ('(ว่าง — ตั้งใจไม่ออก SKU)' if skip else '(ว่าง)')} "
                                f"โดย {self.env.user.name}")
        return {"type": "ir.actions.act_window_close"}


class AzSkuRules(models.TransientModel):
    """Read-only dialog: how a SKU / category code is built."""
    _name = "az.sku.rules"
    _description = "กติกาการตั้งรหัส SKU"
