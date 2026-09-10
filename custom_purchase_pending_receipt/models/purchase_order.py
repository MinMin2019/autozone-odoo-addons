from odoo import api, fields, models
from odoo.tools import float_compare


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    pending_receipt_line_count = fields.Integer(
        string="Pending Receipt Lines",
        compute="_compute_pending_receipt_line_count",
        store=True,
        help="Number of order lines not fully received (confirmed orders only).",
    )
    @api.depends(
        "state",
        "order_line.qty_received",
        "order_line.product_qty",
        "order_line.display_type",
    )
    def _compute_pending_receipt_line_count(self):
        for order in self:
            if order.state not in ("purchase", "done"):
                order.pending_receipt_line_count = 0
                continue
            count = 0
            for line in order.order_line:
                if line.display_type:
                    continue
                rounding = line.product_uom.rounding or 0.01
                if float_compare(
                    line.qty_received, line.product_qty, precision_rounding=rounding
                ) < 0:
                    count += 1
            order.pending_receipt_line_count = count
