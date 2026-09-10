from odoo import models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def button_confirm(self):
        Check = self.env["az.approval.type"]
        for order in self:
            label = "ยืนยันใบสั่งซื้อ %s" % order.name
            Check.check_partners(order.partner_id, label)
            Check.check_products(
                order.order_line.filtered(
                    lambda l: not l.display_type).mapped("product_id"),
                label)
        return super().button_confirm()
