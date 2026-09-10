from odoo import _, api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x_remaining_qty = fields.Float(
        string="Remaining",
        compute="_compute_x_remaining_qty",
        store=True,
        digits="Product Unit of Measure",
    )

    x_is_service_line = fields.Boolean(
        string="Is Service Line",
        compute="_compute_x_is_service_line",
        store=True,
    )

    x_client_order_ref = fields.Char(
        string="Customer Reference",
        related="order_id.client_order_ref",
        store=True,
        index=True,
    )

    x_order_name = fields.Char(
        string="Sales Order",
        related="order_id.name",
        store=True,
        index=True,
    )

    x_partner_id = fields.Many2one(
        string="Customer",
        comodel_name="res.partner",
        related="order_id.partner_id",
        store=True,
        index=True,
    )

    x_due_date = fields.Date(
        string="Due Date",
        compute="_compute_x_due_date",
        store=True,
        index=True,
    )

    x_is_due_today = fields.Boolean(
        string="Due Today",
        compute="_compute_x_due_status",
    )

    x_is_overdue = fields.Boolean(
        string="Overdue",
        compute="_compute_x_due_status",
    )

    x_delivered_add_qty = fields.Float(
        string="Add Delivered",
        digits="Product Unit of Measure",
        help="Quantity to add to delivered quantity.",
    )

    def action_add_delivered_qty(self):
        self.ensure_one()

        if self.display_type:
            return False

        if not self.product_id or self.product_id.type != "service":
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Warning"),
                    "message": _("This action is only allowed for service lines."),
                    "type": "warning",
                    "sticky": False,
                },
            }

        if self.x_delivered_add_qty <= 0:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Warning"),
                    "message": _("Please enter a quantity greater than 0."),
                    "type": "warning",
                    "sticky": False,
                },
            }

        new_total = self.qty_delivered + self.x_delivered_add_qty

        if new_total > self.product_uom_qty:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Warning"),
                    "message": _(
                        "Delivered quantity cannot exceed ordered quantity. "
                        "Ordered: %(ordered)s, Current Delivered: %(delivered)s, "
                        "Trying to Add: %(add)s, New Total: %(new_total)s"
                    )
                    % {
                        "ordered": self.product_uom_qty,
                        "delivered": self.qty_delivered,
                        "add": self.x_delivered_add_qty,
                        "new_total": new_total,
                    },
                    "type": "warning",
                    "sticky": True,
                },
            }

        self.qty_delivered = new_total
        self.x_delivered_add_qty = 0.0

    @api.depends("product_id", "product_id.type", "display_type")
    def _compute_x_is_service_line(self):
        for line in self:
            line.x_is_service_line = bool(
                not line.display_type
                and line.product_id
                and line.product_id.type == "service"
            )

    @api.depends(
        "product_uom_qty",
        "qty_delivered",
        "product_id",
        "product_id.type",
        "display_type",
    )
    def _compute_x_remaining_qty(self):
        for line in self:
            if (
                line.display_type
                or not line.product_id
                or line.product_id.type != "service"
            ):
                line.x_remaining_qty = 0.0
            else:
                remaining = line.product_uom_qty - line.qty_delivered
                line.x_remaining_qty = remaining if remaining > 0 else 0.0

    @api.depends("order_id.commitment_date")
    def _compute_x_due_date(self):
        for line in self:
            line.x_due_date = (
                fields.Date.to_date(line.order_id.commitment_date)
                if line.order_id.commitment_date
                else False
            )

    @api.depends("x_due_date", "x_remaining_qty")
    def _compute_x_due_status(self):
        for line in self:
            today = fields.Date.context_today(line)
            due = line.x_due_date
            has_backlog = line.x_remaining_qty > 0

            line.x_is_due_today = bool(has_backlog and due and due == today)
            line.x_is_overdue = bool(has_backlog and due and due < today)

    def action_open_sale_order(self):
        self.ensure_one()
        if not self.order_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": "Sales Order",
            "res_model": "sale.order",
            "res_id": self.order_id.id,
            "view_mode": "form",
            "target": "current",
        }
