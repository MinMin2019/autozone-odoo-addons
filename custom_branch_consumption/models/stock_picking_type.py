from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    consumption_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Consumption Analytic Account",
        check_company=True,
        help="Applied to the expense line of the valuation entry when consuming "
        "materials through this operation type (cost per branch).",
    )
