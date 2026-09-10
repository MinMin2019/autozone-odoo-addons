from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_post(self):
        # ซ้ำกับด่าน account.move._post แต่ให้ error ชี้ที่ใบจ่าย/รับเงินชัดกว่า
        Check = self.env["az.approval.type"]
        for pay in self:
            if pay.partner_id:
                Check.check_partners(
                    pay.partner_id, "ยืนยันการจ่าย/รับเงิน %s" % pay.display_name)
        return super().action_post()
