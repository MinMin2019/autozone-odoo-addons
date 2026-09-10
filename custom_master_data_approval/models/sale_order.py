from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        Check = self.env["az.approval.type"]
        for order in self:
            label = "ยืนยันใบสั่งขาย %s" % order.name
            partners = (order.partner_id | order.partner_invoice_id
                        | order.partner_shipping_id)
            Check.check_partners(partners, label)
            Check.check_products(
                order.order_line.filtered(
                    lambda l: not l.display_type).mapped("product_id"),
                label)
        return super().action_confirm()
