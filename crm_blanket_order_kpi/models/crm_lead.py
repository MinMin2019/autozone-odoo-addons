# Copyright 2026
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class CrmLead(models.Model):
    """Opportunity = control tower for the main contract flow (Flow A):

    Quotation (source) -> Blanket Order -> SO Release -> Invoice.

    KPIs only count documents that belong to the Blanket Order chain.
    Small additional jobs without a BO (Flow B) stay out of the summary.
    """

    _inherit = "crm.lead"

    # --- Links ---------------------------------------------------------------
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="โปรเจกต์ (Project / Analytic)",
        help="โปรเจกต์ที่เป็นแกนกลาง ส่งต่อ (propagate) ลงไปยัง Blanket Order / "
        "Release / Invoice ผ่าน analytic distribution.\n\n"
        "(EN) Project backbone. Propagated down to Blanket Orders / Releases / "
        "Invoices through the analytic distribution.",
    )
    source_quotation_ids = fields.Many2many(
        "sale.order",
        string="ใบเสนอราคาสัญญา (Contract Quotations)",
        compute="_compute_source_quotation_ids",
        help="ใบเสนอราคาที่ติ๊ก Contract Source ไว้ เป็นต้นทางของ Quoted Qty และ "
        "Expected Revenue.\n\n"
        "(EN) Quotations flagged as contract source. They feed Quoted Qty and "
        "Expected Revenue.",
    )
    blanket_order_ids = fields.One2many(
        "sale.blanket.order",
        "opportunity_id",
        string="Blanket Orders (สัญญาแม่)",
    )

    # --- KPI ------------------------------------------------------------------
    quoted_qty = fields.Float(
        string="ยอดเสนอ (Quoted Qty)",
        compute="_compute_quoted",
        store=True,
        digits="Product Unit of Measure",
        help="เพดานที่เสนอลูกค้า = ผลรวมบรรทัดของใบเสนอราคาสัญญาทุกใบ.\n\n"
        "(EN) Ceiling offered to the customer = sum of contract quotation lines.",
    )
    quoted_amount = fields.Monetary(
        string="มูลค่าเสนอ (Quoted Amount)",
        compute="_compute_quoted",
        store=True,
        currency_field="company_currency",
    )
    contract_qty = fields.Float(
        string="ยอดสัญญา (Contract Qty)",
        compute="_compute_contract",
        store=True,
        digits="Product Unit of Measure",
        help="จำนวนที่แตกเป็น Blanket Order (ที่ confirm แล้ว).\n\n"
        "(EN) Quantity actually carved into confirmed Blanket Orders.",
    )
    released_qty = fields.Float(
        string="ยอดเรียกแล้ว (Released Qty)",
        compute="_compute_contract",
        store=True,
        digits="Product Unit of Measure",
        help="จำนวนที่เรียกผ่าน SO Release ของ Blanket Order.\n\n"
        "(EN) Quantity called off through SO Releases of the Blanket Orders.",
    )
    invoiced_qty = fields.Float(
        string="ยอดวางบิล (Invoiced Qty)",
        compute="_compute_invoiced",
        store=True,
        digits="Product Unit of Measure",
        help="จำนวนบน invoice ที่ posted แล้ว ซึ่ง trace กลับ BO chain ได้.\n\n"
        "(EN) Quantity on posted invoice lines traceable to the BO chain.",
    )
    invoiced_amount = fields.Monetary(
        string="มูลค่าวางบิล (Invoiced Amount)",
        compute="_compute_invoiced",
        store=True,
        currency_field="company_currency",
    )
    remaining_to_bo_qty = fields.Float(
        string="คงเหลือรอแตก BO (Remaining to BO)",
        compute="_compute_remaining",
        store=True,
        digits="Product Unit of Measure",
        help="Quoted − Contract: ยังเหลือให้แตกเป็น Blanket Order (งวดถัดไป).\n\n"
        "(EN) Quoted Qty - Contract Qty: still available to carve into new "
        "Blanket Orders (next periods).",
    )
    remaining_release_qty = fields.Float(
        string="คงเหลือรอเรียก (Remaining to Release)",
        compute="_compute_remaining",
        store=True,
        digits="Product Unit of Measure",
        help="Contract − Released: ยังเหลือให้เรียกภายใน Blanket Order ที่ออกแล้ว.\n\n"
        "(EN) Contract Qty - Released Qty: still to be called off within the "
        "confirmed Blanket Orders.",
    )
    released_amount = fields.Monetary(
        string="มูลค่าเรียกแล้ว (Released Amount)",
        compute="_compute_to_invoice",
        store=True,
        currency_field="company_currency",
    )
    to_invoice_qty = fields.Float(
        string="ยอดค้างวางบิล (To Invoice Qty)",
        compute="_compute_to_invoice",
        store=True,
        digits="Product Unit of Measure",
        help="Released − Invoiced: เรียกของแล้วแต่ยังไม่ได้วางบิล (posted) — "
        "ยอดที่รอเก็บเงิน.\n\n"
        "(EN) Released - Invoiced: called off but not yet billed (posted).",
    )
    to_invoice_amount = fields.Monetary(
        string="มูลค่าค้างวางบิล (To Invoice Amount)",
        compute="_compute_to_invoice",
        store=True,
        currency_field="company_currency",
    )

    # --- Smart button counts --------------------------------------------------
    contract_quotation_count = fields.Integer(compute="_compute_chain_counts")
    blanket_order_count = fields.Integer(compute="_compute_chain_counts")
    release_count = fields.Integer(compute="_compute_chain_counts")
    contract_invoice_count = fields.Integer(compute="_compute_chain_counts")

    # =========================================================================
    # Computes
    # =========================================================================
    @api.depends("order_ids.is_contract_source")
    def _compute_source_quotation_ids(self):
        for lead in self:
            lead.source_quotation_ids = lead.order_ids.filtered("is_contract_source")

    @api.depends(
        "order_ids.is_contract_source",
        "order_ids.amount_untaxed",
        "order_ids.order_line.product_uom_qty",
        "order_ids.order_line.display_type",
    )
    def _compute_quoted(self):
        # Depend on the real order_ids relation (not the computed
        # source_quotation_ids) so the stored value recomputes when a contract
        # quotation changes.
        for lead in self:
            quotes = lead.order_ids.filtered("is_contract_source")
            lines = quotes.order_line.filtered(lambda line: not line.display_type)
            lead.quoted_qty = sum(lines.mapped("product_uom_qty"))
            lead.quoted_amount = sum(quotes.mapped("amount_untaxed"))

    @api.depends(
        "blanket_order_ids.state",
        "blanket_order_ids.line_ids.original_uom_qty",
        "blanket_order_ids.line_ids.ordered_uom_qty",
        "blanket_order_ids.line_ids.display_type",
    )
    def _compute_contract(self):
        for lead in self:
            bo_lines = lead._get_contract_bo_lines()
            lead.contract_qty = sum(bo_lines.mapped("original_uom_qty"))
            lead.released_qty = sum(bo_lines.mapped("ordered_uom_qty"))

    @api.depends(
        "blanket_order_ids.state",
        "blanket_order_ids.line_ids.invoiced_qty_posted",
        "blanket_order_ids.line_ids.invoiced_amount_posted",
        "blanket_order_ids.line_ids.display_type",
    )
    def _compute_invoiced(self):
        # Posted-only invoiced figures are computed per BO line (the granular
        # fact) and rolled up here, so Opportunity and the per-product report
        # stay consistent.
        for lead in self:
            bo_lines = lead._get_contract_bo_lines()
            lead.invoiced_qty = sum(bo_lines.mapped("invoiced_qty_posted"))
            lead.invoiced_amount = sum(bo_lines.mapped("invoiced_amount_posted"))

    @api.depends(
        "blanket_order_ids.state",
        "blanket_order_ids.line_ids.to_invoice_qty",
        "blanket_order_ids.line_ids.to_invoice_amount",
        "blanket_order_ids.line_ids.released_amount",
        "blanket_order_ids.line_ids.display_type",
    )
    def _compute_to_invoice(self):
        for lead in self:
            bo_lines = lead._get_contract_bo_lines()
            lead.released_amount = sum(bo_lines.mapped("released_amount"))
            lead.to_invoice_qty = sum(bo_lines.mapped("to_invoice_qty"))
            lead.to_invoice_amount = sum(bo_lines.mapped("to_invoice_amount"))

    @api.depends("quoted_qty", "contract_qty", "released_qty")
    def _compute_remaining(self):
        for lead in self:
            lead.remaining_to_bo_qty = lead.quoted_qty - lead.contract_qty
            lead.remaining_release_qty = lead.contract_qty - lead.released_qty

    @api.depends(
        "source_quotation_ids",
        "blanket_order_ids",
        "blanket_order_ids.line_ids.sale_lines",
    )
    def _compute_chain_counts(self):
        for lead in self:
            lead.contract_quotation_count = len(lead.source_quotation_ids)
            lead.blanket_order_count = len(lead.blanket_order_ids)
            lead.release_count = len(lead._get_release_orders())
            lead.contract_invoice_count = len(lead._get_posted_invoices())

    # =========================================================================
    # Helpers
    # =========================================================================
    def _get_contract_bo_lines(self):
        """Accountable BO lines of confirmed Blanket Orders."""
        self.ensure_one()
        boms = self.blanket_order_ids.filtered(lambda bo: bo.state != "draft")
        return boms.line_ids.filtered(lambda line: not line.display_type)

    def _get_remaining_to_bo_by_product(self):
        """Map product_id -> qty still available to carve into a Blanket Order.

        remaining = quoted (contract quotation lines) - already carved (all BO
        lines, drafts included so pending drafts still reserve their share)."""
        self.ensure_one()
        remaining = {}
        for line in self.source_quotation_ids.order_line.filtered(
            lambda l: not l.display_type
        ):
            remaining[line.product_id.id] = (
                remaining.get(line.product_id.id, 0.0) + line.product_uom_qty
            )
        for bol in self.blanket_order_ids.line_ids.filtered(
            lambda l: not l.display_type
        ):
            if bol.product_id.id in remaining:
                remaining[bol.product_id.id] -= bol.original_uom_qty
        return remaining

    def _get_release_orders(self):
        self.ensure_one()
        return self.blanket_order_ids.line_ids.sale_lines.order_id.filtered(
            lambda so: so.state != "cancel"
        )

    def _get_posted_invoices(self):
        self.ensure_one()
        moves = self.env["account.move"]
        for bol in self._get_contract_bo_lines():
            for move_line in bol.sale_lines.invoice_lines:
                move = move_line.move_id
                if move.state == "posted" and move.move_type in (
                    "out_invoice",
                    "out_refund",
                ):
                    moves |= move
        return moves

    # =========================================================================
    # Expected revenue: driven by source quotations, not by every linked SO
    # =========================================================================
    def _sync_contract_expected_revenue(self):
        for lead in self:
            if lead.source_quotation_ids:
                amount = sum(lead.source_quotation_ids.mapped("amount_untaxed"))
                if lead.expected_revenue != amount:
                    lead.expected_revenue = amount

    def _update_revenues_from_so(self, order):
        # Flow B / standard opportunities keep the native behaviour; contract
        # opportunities take Expected Revenue from their source quotations only.
        contract = self.filtered(lambda lead: lead.source_quotation_ids)
        super(CrmLead, self - contract)._update_revenues_from_so(order)
        contract._sync_contract_expected_revenue()

    # =========================================================================
    # Smart button actions
    # =========================================================================
    def action_view_contract_quotations(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_quotations_with_onboarding")
        action["domain"] = [("id", "in", self.source_quotation_ids.ids)]
        action["context"] = {"default_opportunity_id": self.id}
        return action

    def action_view_blanket_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sale_blanket_order.act_open_blanket_order_view"
        )
        action["domain"] = [("id", "in", self.blanket_order_ids.ids)]
        action["context"] = {"default_opportunity_id": self.id}
        return action

    def action_view_releases(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_orders")
        action["domain"] = [("id", "in", self._get_release_orders().ids)]
        action["context"] = {}
        return action

    def action_view_contract_invoices(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_invoice_type")
        action["domain"] = [("id", "in", self._get_posted_invoices().ids)]
        action["context"] = {"default_move_type": "out_invoice"}
        return action

    def action_view_contract_timeline(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "crm_blanket_order_kpi.action_contract_timeline_report"
        )
        action["domain"] = [("opportunity_id", "=", self.id)]
        action["context"] = {"search_default_group_year": 1}
        return action
