from odoo import api, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    @api.model
    def _get_date_planned(self, seller, po=False):
        # Once the order already has an Expected Arrival date, new/updated
        # lines inherit it instead of recomputing from vendor lead time,
        # so adding a product never shifts the order-level date.
        order = po or self.order_id
        if order and order.date_planned:
            return order.date_planned
        return super()._get_date_planned(seller, po=po)
