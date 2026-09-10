# Copyright 2026
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class CrmBlanketOrderCreateWizard(models.TransientModel):
    _name = "crm.blanket.order.create.wizard"
    _description = "Carve a Blanket Order from a contract quotation"

    quotation_id = fields.Many2one(
        "sale.order",
        string="ใบเสนอราคาต้นทาง (Source Quotation)",
        required=True,
        readonly=True,
    )
    opportunity_id = fields.Many2one(
        related="quotation_id.opportunity_id",
        string="Opportunity (โอกาสการขาย)",
    )
    validity_date = fields.Date(
        string="วันหมดอายุ (Validity Date)",
        required=True,
        default=lambda self: fields.Date.context_today(self)
        + relativedelta(years=1),
    )
    line_ids = fields.One2many(
        "crm.blanket.order.create.wizard.line",
        "wizard_id",
        string="Lines",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        quotation_id = res.get("quotation_id") or self.env.context.get(
            "default_quotation_id"
        )
        if quotation_id and "line_ids" in fields_list:
            quotation = self.env["sale.order"].browse(quotation_id)
            res["line_ids"] = self._prepare_wizard_lines(quotation)
        return res

    @api.model
    def _prepare_wizard_lines(self, quotation):
        """One wizard line per accountable quotation line, defaulting the qty to
        what is still available to carve into a Blanket Order for that product."""
        remaining_by_product = quotation.opportunity_id._get_remaining_to_bo_by_product()
        commands = []
        for line in quotation.order_line.filtered(lambda l: not l.display_type):
            product = line.product_id
            available = remaining_by_product.get(product.id, 0.0)
            qty = max(0.0, min(line.product_uom_qty, available))
            # consume so two lines of the same product don't both grab the full
            # remaining amount
            remaining_by_product[product.id] = available - qty
            commands.append(
                fields.Command.create(
                    {
                        "order_line_id": line.id,
                        "qty": qty,
                    }
                )
            )
        return commands

    def action_create_blanket_order(self):
        self.ensure_one()
        quotation = self.quotation_id
        opportunity = quotation.opportunity_id
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        lines = self.line_ids.filtered(
            lambda wl: float_compare(wl.qty, 0.0, precision_digits=precision) > 0
        )
        if not lines:
            raise UserError(self.env._("Nothing to carve: all quantities are zero."))

        # Ceiling guard: carved (existing BOs) + this BO must not exceed quoted.
        remaining_by_product = opportunity._get_remaining_to_bo_by_product()
        requested = {}
        for wl in lines:
            requested.setdefault(wl.product_id.id, 0.0)
            requested[wl.product_id.id] += wl.qty
        for product_id, qty in requested.items():
            available = remaining_by_product.get(product_id, 0.0)
            if float_compare(qty, available, precision_digits=precision) > 0:
                product = self.env["product.product"].browse(product_id)
                raise UserError(
                    self.env._(
                        "Cannot carve %(req)s of %(product)s: only %(avail)s "
                        "remain under the quoted ceiling. Open a supplementary "
                        "contract quotation to raise it.",
                        req=qty,
                        product=product.display_name,
                        avail=available,
                    )
                )

        # ด่านอนุมัติข้อมูลหลัก (ทำงานเฉพาะเมื่อติดตั้ง custom_master_data_approval)
        # — BO confirm ไม่ได้ถูก hook ตรง แต่ SO ที่ release ถูกดักที่ action_confirm
        # อยู่แล้ว ตรงนี้กันไว้ตั้งแต่ตอน carve เพื่อ fail-fast
        if "az.approval.type" in self.env:
            check = self.env["az.approval.type"]
            check.check_partners(quotation.partner_id, "สร้าง Blanket Order")
            check.check_products(lines.mapped("product_id"), "สร้าง Blanket Order")

        bo = self.env["sale.blanket.order"].create(self._prepare_bo_vals(lines))
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sale_blanket_order.act_open_blanket_order_view"
        )
        action.update(
            {
                "view_mode": "form",
                "views": [(False, "form")],
                "res_id": bo.id,
            }
        )
        return action

    def _prepare_bo_vals(self, lines):
        quotation = self.quotation_id
        opportunity = quotation.opportunity_id
        analytic = opportunity.analytic_account_id
        pricelist = (
            quotation.pricelist_id
            or quotation.partner_id.property_product_pricelist
        )
        if not pricelist:
            raise UserError(
                self.env._(
                    "No pricelist found on quotation %s; a Blanket Order "
                    "requires one." % quotation.name
                )
            )
        distribution = {str(analytic.id): 100.0} if analytic else False
        line_vals = []
        for wl in lines:
            src = wl.order_line_id
            line_vals.append(
                fields.Command.create(
                    {
                        "product_id": src.product_id.id,
                        "name": src.name,
                        "product_uom": src.product_uom.id,
                        "original_uom_qty": wl.qty,
                        "price_unit": src.price_unit,
                        "taxes_id": [fields.Command.set(src.tax_id.ids)],
                        "analytic_distribution": distribution,
                    }
                )
            )
        return {
            "partner_id": quotation.partner_id.id,
            "pricelist_id": pricelist.id,
            "payment_term_id": quotation.payment_term_id.id,
            "user_id": quotation.user_id.id,
            "team_id": quotation.team_id.id,
            "validity_date": self.validity_date,
            "opportunity_id": opportunity.id,
            "source_quotation_id": quotation.id,
            "client_order_ref": quotation.client_order_ref,
            "line_ids": line_vals,
        }


class CrmBlanketOrderCreateWizardLine(models.TransientModel):
    _name = "crm.blanket.order.create.wizard.line"
    _description = "Create Blanket Order wizard line"

    wizard_id = fields.Many2one(
        "crm.blanket.order.create.wizard", required=True, ondelete="cascade"
    )
    order_line_id = fields.Many2one(
        "sale.order.line", string="Quotation Line", required=True, readonly=True
    )
    product_id = fields.Many2one(
        related="order_line_id.product_id", string="Product", readonly=True
    )
    product_uom = fields.Many2one(
        related="order_line_id.product_uom", string="UoM", readonly=True
    )
    quoted_qty = fields.Float(
        related="order_line_id.product_uom_qty",
        string="ยอดเสนอ (Quoted Qty)",
        readonly=True,
    )
    qty = fields.Float(
        string="จำนวนที่จะแตก (Qty to Carve)",
        digits="Product Unit of Measure",
        required=True,
    )
