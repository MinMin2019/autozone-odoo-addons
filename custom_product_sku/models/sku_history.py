from odoo import fields, models


class AzSkuHistory(models.Model):
    """Every SKU ever handed out — kept even when the product is deleted, so it is never reused."""
    _name = "az.sku.history"
    _description = "ประวัติ SKU"
    _order = "date desc, id desc"
    _rec_name = "sku"

    sku = fields.Char("SKU", required=True, index=True, readonly=True)
    product_tmpl_id = fields.Many2one("product.template", "สินค้า", ondelete="set null", index=True, readonly=True)
    product_name = fields.Char("ชื่อสินค้า (ตอนออกรหัส)", readonly=True)
    action = fields.Selection(
        [("issue", "ออกรหัส"), ("retire", "เลิกใช้ (ออกรหัสใหม่)"), ("cancel", "ยกเลิก SKU")],
        "รายการ", required=True, readonly=True)
    reason = fields.Char("เหตุผล", readonly=True)
    label_printed = fields.Boolean("พิมพ์ฉลากไปแล้ว", readonly=True)
    user_id = fields.Many2one("res.users", "ผู้ทำ", default=lambda self: self.env.user, readonly=True)
    date = fields.Datetime("วันที่", default=fields.Datetime.now, readonly=True)
