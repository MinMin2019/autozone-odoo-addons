# Copyright 2026
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import fields, models, tools


class CrmContractTimelineReport(models.Model):
    """Read-only SQL report: contract execution events over time.

    Each row is one event - either a SO Release line (event_type='released')
    or a posted invoice line (event_type='invoiced') - that belongs to a
    Blanket Order chain of an Opportunity. Pivot by date (year/quarter) x
    event_type to see how a multi-year contract is consumed and billed.
    """

    _name = "crm.contract.timeline.report"
    _description = "Contract Timeline (Released vs Invoiced)"
    _auto = False
    _order = "date desc"

    opportunity_id = fields.Many2one("crm.lead", string="Opportunity", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    date = fields.Date(string="Date", readonly=True)
    event_type = fields.Selection(
        [
            ("released", "เรียกแล้ว / Released"),
            ("invoiced", "วางบิล / Invoiced"),
        ],
        string="Event",
        readonly=True,
    )
    product_qty = fields.Float(string="จำนวน / Quantity", readonly=True)
    amount_untaxed = fields.Monetary(
        string="มูลค่า / Amount", readonly=True, currency_field="currency_id"
    )
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"""
            CREATE VIEW {self._table} AS (
                SELECT
                    row_number() OVER () AS id,
                    sub.opportunity_id,
                    sub.partner_id,
                    sub.product_id,
                    sub.date,
                    sub.event_type,
                    sub.product_qty,
                    sub.amount_untaxed,
                    sub.company_id,
                    rc.currency_id AS currency_id
                FROM (
                    -- SO Release lines linked to a BO of an opportunity
                    SELECT
                        bo.opportunity_id AS opportunity_id,
                        so.partner_id AS partner_id,
                        sol.product_id AS product_id,
                        (so.date_order)::date AS date,
                        'released'::text AS event_type,
                        sol.product_uom_qty AS product_qty,
                        sol.price_subtotal AS amount_untaxed,
                        so.company_id AS company_id
                    FROM sale_order_line sol
                    JOIN sale_blanket_order_line bol
                        ON sol.blanket_order_line = bol.id
                    JOIN sale_blanket_order bo ON bol.order_id = bo.id
                    JOIN sale_order so ON sol.order_id = so.id
                    WHERE bo.opportunity_id IS NOT NULL
                        AND so.state <> 'cancel'
                        AND sol.display_type IS NULL

                    UNION ALL

                    -- Posted invoice lines traced to a BO of an opportunity
                    SELECT
                        bo.opportunity_id AS opportunity_id,
                        am.partner_id AS partner_id,
                        aml.product_id AS product_id,
                        COALESCE(am.invoice_date, am.date)::date AS date,
                        'invoiced'::text AS event_type,
                        (CASE WHEN am.move_type = 'out_refund'
                              THEN -aml.quantity ELSE aml.quantity END)
                            AS product_qty,
                        (CASE WHEN am.move_type = 'out_refund'
                              THEN -aml.price_subtotal ELSE aml.price_subtotal END)
                            AS amount_untaxed,
                        am.company_id AS company_id
                    FROM account_move_line aml
                    JOIN account_move am ON aml.move_id = am.id
                    JOIN sale_order_line_invoice_rel rel
                        ON rel.invoice_line_id = aml.id
                    JOIN sale_order_line sol ON rel.order_line_id = sol.id
                    JOIN sale_blanket_order_line bol
                        ON sol.blanket_order_line = bol.id
                    JOIN sale_blanket_order bo ON bol.order_id = bo.id
                    WHERE bo.opportunity_id IS NOT NULL
                        AND am.state = 'posted'
                        AND am.move_type IN ('out_invoice', 'out_refund')
                ) sub
                JOIN res_company rc ON rc.id = sub.company_id
            )
            """
        )
