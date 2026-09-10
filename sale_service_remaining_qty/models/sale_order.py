from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    x_service_remaining_total = fields.Float(
        string="Remaining",
        compute="_compute_x_service_totals",
        store=True,
        digits="Product Unit of Measure",
    )

    x_service_delivered_total = fields.Float(
        string="Delivered",
        compute="_compute_x_service_totals",
        store=True,
        digits="Product Unit of Measure",
    )

    x_service_backlog_count = fields.Integer(
        string="Order Backlog Count",
        compute="_compute_x_service_totals",
        store=True,
    )

    @api.depends(
        "order_line.x_remaining_qty",
        "order_line.qty_delivered",
        "order_line.product_id",
        "order_line.product_id.type",
        "order_line.display_type",
    )
    def _compute_x_service_totals(self):
        for order in self:
            service_lines = order.order_line.filtered(
                lambda l: not l.display_type and l.product_id and l.product_id.type == "service"
            )
            order.x_service_delivered_total = sum(service_lines.mapped("qty_delivered"))
            order.x_service_remaining_total = sum(service_lines.mapped("x_remaining_qty"))
            order.x_service_backlog_count = len(
                service_lines.filtered(lambda l: l.x_remaining_qty > 0)
            )

    def action_view_service_backlog_lines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Order Backlog",
            "res_model": "sale.order.line",
            "view_mode": "list",
            "views": [(self.env.ref("sale_service_remaining_qty.view_sale_order_line_service_backlog_list").id, "list")],
            "target": "current",
            "domain": [
                ("order_id", "=", self.id),
                ("x_is_service_line", "=", True),
                ("x_remaining_qty", ">", 0),
            ],
            "context": {
                "create": False,
                "edit": False,
                "delete": False,
            },
        }
