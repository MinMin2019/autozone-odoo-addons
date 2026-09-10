# Copyright 2026
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class SaleBlanketOrder(models.Model):
    _inherit = "sale.blanket.order"

    opportunity_id = fields.Many2one(
        "crm.lead",
        string="Opportunity (โอกาสการขาย)",
        copy=False,
        index=True,
        domain="[('type', '=', 'opportunity')]",
        help="Opportunity ที่เป็น control tower และ Blanket Order นี้ส่งยอดไปรวม.\n\n"
        "(EN) Control-tower opportunity this Blanket Order rolls up to.",
    )
    source_quotation_id = fields.Many2one(
        "sale.order",
        string="ใบเสนอราคาต้นทาง (Source Quotation)",
        copy=False,
        help="ใบเสนอราคาสัญญาที่ Blanket Order นี้ถูกแตกออกมา.\n\n"
        "(EN) Contract quotation this Blanket Order was carved from.",
    )


class SaleBlanketOrderLine(models.Model):
    _inherit = "sale.blanket.order.line"

    opportunity_id = fields.Many2one(
        related="order_id.opportunity_id",
        string="Opportunity (โอกาสการขาย)",
        store=True,
        index=True,
    )
    invoiced_qty_posted = fields.Float(
        string="ยอดวางบิล-Posted (Invoiced Qty Posted)",
        compute="_compute_invoiced_posted",
        store=True,
        digits="Product Unit of Measure",
        help="จำนวนที่วางบิลผ่าน invoice/credit note ที่ posted แล้ว และ trace กลับ "
        "บรรทัดสัญญานี้ได้ (out_invoice +, out_refund −).\n\n"
        "(EN) Quantity invoiced through *posted* customer invoices/credit notes "
        "traceable to this contract line (out_invoice +, out_refund -).",
    )
    invoiced_amount_posted = fields.Monetary(
        string="มูลค่าวางบิล-Posted (Invoiced Amount Posted)",
        compute="_compute_invoiced_posted",
        store=True,
        currency_field="currency_id",
    )
    released_amount = fields.Monetary(
        string="มูลค่าเรียกแล้ว (Released Amount)",
        compute="_compute_released_amount",
        store=True,
        currency_field="currency_id",
        help="มูลค่ารวมของ SO Release (ที่ไม่ถูกยกเลิก) ของบรรทัดสัญญานี้.\n\n"
        "(EN) Total value of the (non-cancelled) SO Releases of this line.",
    )
    to_invoice_qty = fields.Float(
        string="ยอดค้างวางบิล (To Invoice Qty)",
        compute="_compute_to_invoice",
        store=True,
        digits="Product Unit of Measure",
        help="Released − Invoiced: เรียกของแล้วแต่ยังไม่ได้วางบิล (posted).\n\n"
        "(EN) Released - Invoiced: called off but not yet billed (posted).",
    )
    to_invoice_amount = fields.Monetary(
        string="มูลค่าค้างวางบิล (To Invoice Amount)",
        compute="_compute_to_invoice",
        store=True,
        currency_field="currency_id",
    )

    @api.depends("sale_lines.price_subtotal", "sale_lines.order_id.state")
    def _compute_released_amount(self):
        for line in self:
            line.released_amount = sum(
                sl.price_subtotal
                for sl in line.sale_lines
                if sl.order_id.state != "cancel"
            )

    @api.depends(
        "ordered_uom_qty",
        "invoiced_qty_posted",
        "released_amount",
        "invoiced_amount_posted",
    )
    def _compute_to_invoice(self):
        for line in self:
            line.to_invoice_qty = line.ordered_uom_qty - line.invoiced_qty_posted
            line.to_invoice_amount = line.released_amount - line.invoiced_amount_posted

    @api.depends(
        "sale_lines.invoice_lines.parent_state",
        "sale_lines.invoice_lines.quantity",
        "sale_lines.invoice_lines.price_subtotal",
        "sale_lines.order_id.state",
        "product_uom",
    )
    def _compute_invoiced_posted(self):
        for line in self:
            qty = 0.0
            amount = 0.0
            for sale_line in line.sale_lines:
                if sale_line.order_id.state == "cancel":
                    continue
                for move_line in sale_line.invoice_lines:
                    move = move_line.move_id
                    if move.state != "posted" or move.move_type not in (
                        "out_invoice",
                        "out_refund",
                    ):
                        continue
                    sign = 1.0 if move.move_type == "out_invoice" else -1.0
                    line_qty = move_line.quantity
                    if move_line.product_uom_id and line.product_uom:
                        line_qty = move_line.product_uom_id._compute_quantity(
                            move_line.quantity, line.product_uom
                        )
                    qty += sign * line_qty
                    amount += sign * move_line.price_subtotal
            line.invoiced_qty_posted = qty
            line.invoiced_amount_posted = amount
