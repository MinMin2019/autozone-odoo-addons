from odoo import fields, models


class AccountPaymentMethodLine(models.Model):
    _inherit = "account.payment.method.line"

    # ฝ่ายบัญชีกำหนดให้บัญชีพักเงินสดย่อยเป็นประเภท "เงินสด" (asset_cash)
    # แต่ domain มาตรฐานของ Odoo ยอมเฉพาะ asset_current/liability_current
    # ทำให้เลือกในหน้าจอ journal ไม่ได้ — เปิด asset_cash เพิ่มในตัวกรอง
    payment_account_id = fields.Many2one(
        domain="[('deprecated', '=', False), "
        "'|', ('account_type', 'in', ('asset_current', 'liability_current', 'asset_cash')), "
        "('id', '=', default_account_id)]",
    )
