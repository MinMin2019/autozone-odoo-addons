from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    def action_create_payments(self):
        # ดักตั้งแต่ wizard (petty cash เรียก wizard นี้ตรง ๆ) — ให้ error โผล่
        # ก่อนสร้าง payment แทนที่จะไปตายกลางทางตอน post
        partners = self.line_ids.move_id.mapped("partner_id")
        self.env["az.approval.type"].check_partners(partners, "จ่าย/รับเงิน")
        return super().action_create_payments()
