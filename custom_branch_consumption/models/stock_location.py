from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    is_expense_consumption = fields.Boolean(
        string="Consumption to Expense",
        help="Moves into this location post the cost to the product category's "
        "expense account instead of the Stock Output account (internal material "
        "consumption, not a sale).",
    )
