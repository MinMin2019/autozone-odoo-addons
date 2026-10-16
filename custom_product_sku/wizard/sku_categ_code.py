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
    current_code = fields.Char(related="categ_id.az_sku_code", string="รหัสปัจจุบัน")
    suggest = fields.Char(related="categ_id.az_sku_code_suggest", string="รหัสที่ว่างถัดไป")
    code = fields.Char("รหัสใหม่ (4 หลัก)", size=4, help="ว่าง = หมวดนี้ไม่ออก SKU ให้สินค้าใหม่")
    skip = fields.Boolean("หมวดนี้ไม่ออก SKU (ตั้งใจ)",
                          default=lambda self: self.env["product.category"].browse(
                              self.env.context.get("default_categ_id")).az_sku_skip,
                          help="ติ๊กเมื่อหมวดนี้ไม่ต้องมี SKU — ระบบจะไม่เตือนให้ตั้งรหัสอีก")
    todo_count = fields.Integer(related="categ_id.az_sku_todo_count", string="สินค้าที่จะได้ SKU")
    done_count = fields.Integer(related="categ_id.az_sku_done_count", string="มี SKU แล้ว")
    sibling_info = fields.Text("หมวดข้างเคียงที่มีรหัสแล้ว", compute="_compute_sibling_info")
    code_warning = fields.Char(compute="_compute_code_warning")

    def _siblings(self):
        self.ensure_one()
        parent = self.categ_id.parent_id
        if not parent:
            return self.env["product.category"]
        return parent.sudo().child_id.filtered(lambda c: c.az_sku_code and c != self.categ_id).sorted("az_sku_code")

    @api.depends("categ_id")
    def _compute_sibling_info(self):
        for wiz in self:
            sibs = wiz._siblings()
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
                    heads = set(sibs.mapped(lambda c: c.az_sku_code[:2]))
                    if heads and code[:2] not in heads:
                        msg.append("2 หลักแรกไม่ตรงกับหมวดข้างเคียง (%s) — ตรวจอีกครั้ง"
                                   % ", ".join(h + "xx" for h in sorted(heads)))
                    if code[2:] == "00":
                        msg.append("หลัก 3-4 ต้องเป็น 01-99 (00 ไม่ใช้)")
                    if code in used and used[code] != wiz.categ_id.complete_name:
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
        categ = self.categ_id.sudo()
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
