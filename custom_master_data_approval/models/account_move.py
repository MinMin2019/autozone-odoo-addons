from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        # จุดคุมใหญ่สุด: hook ที่ _post (ไม่ใช่ action_post) เพื่อดักการ post
        # แบบโปรแกรมด้วย เช่น petty cash / payroll / wizard จ่ายเงิน
        Check = self.env["az.approval.type"]
        for move in self:
            label = "บันทึกบัญชี %s" % (move.name if move.name != "/" else move.display_name)
            if move.partner_id:
                Check.check_partners(move.partner_id, label)
            products = move.line_ids.mapped("product_id")
            if products:
                Check.check_products(products, label)
        return super()._post(soft=soft)
