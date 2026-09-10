# Copyright 2026
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_contract_source = fields.Boolean(
        string="ต้นทางสัญญา (Contract Source)",
        copy=False,
        help="ติ๊กเมื่อใบเสนอราคานี้เป็นต้นทางของสัญญาหลัก (Flow A): ใบนี้จะถูกนับเข้า "
        "Quoted Qty / Expected Revenue ของ Opportunity และใช้ปุ่มสร้าง Blanket "
        "Order ได้ — แต่จะ Confirm เป็น Sale Order เองไม่ได้ (ต้องแตกเป็น Blanket "
        "Order แทน). ใบงานย่อยทั่วไป (Flow B) ไม่ต้องติ๊ก.\n\n"
        "(EN) This quotation is the commercial source of a contract "
        "(Opportunity KPI). It defines Quoted Qty / Expected Revenue and is "
        "the origin of Blanket Orders. It must not be confirmed into a Sale "
        "Order itself - carve Blanket Orders from it instead.",
    )
    blanket_order_ids = fields.One2many(
        "sale.blanket.order",
        "source_quotation_id",
        string="Blanket Orders (สัญญาแม่)",
    )
    blanket_order_count = fields.Integer(compute="_compute_bo_carved")
    carved_to_bo_qty = fields.Float(
        string="แตกเป็น BO แล้ว (Carved to BO)",
        compute="_compute_bo_carved",
        digits="Product Unit of Measure",
        help="จำนวนของใบเสนอราคานี้ที่ถูกแตกเป็น Blanket Order ไปแล้ว.\n\n"
        "(EN) Quantity of this quotation already carved into Blanket Orders.",
    )
    remaining_to_bo_qty = fields.Float(
        string="เหลือรอแตก BO (Remaining to BO)",
        compute="_compute_bo_carved",
        digits="Product Unit of Measure",
        help="ยอดเสนอ − แตกแล้ว: ยังเหลือให้แตกเป็น Blanket Order อีกเท่าไร.\n\n"
        "(EN) Quoted - Carved: still available to carve into Blanket Orders.",
    )

    @api.depends(
        "blanket_order_ids",
        "blanket_order_ids.line_ids.original_uom_qty",
        "blanket_order_ids.line_ids.display_type",
        "order_line.product_uom_qty",
        "order_line.display_type",
    )
    def _compute_bo_carved(self):
        for order in self:
            order.blanket_order_count = len(order.blanket_order_ids)
            carved = sum(
                order.blanket_order_ids.line_ids.filtered(
                    lambda line: not line.display_type
                ).mapped("original_uom_qty")
            )
            quoted = sum(
                order.order_line.filtered(
                    lambda line: not line.display_type
                ).mapped("product_uom_qty")
            )
            order.carved_to_bo_qty = carved
            order.remaining_to_bo_qty = quoted - carved

    def action_view_blanket_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sale_blanket_order.act_open_blanket_order_view"
        )
        action["domain"] = [("id", "in", self.blanket_order_ids.ids)]
        action["context"] = {}
        return action

    @api.constrains("is_contract_source", "opportunity_id")
    def _check_contract_source_opportunity(self):
        for order in self:
            if order.is_contract_source and not order.opportunity_id:
                raise ValidationError(
                    self.env._(
                        "A contract source quotation must be linked to an "
                        "Opportunity."
                    )
                )

    def action_confirm(self):
        for order in self:
            if order.is_contract_source:
                raise UserError(
                    self.env._(
                        "%s is a contract source quotation. Create Blanket "
                        "Orders from it instead of confirming it as a Sale "
                        "Order."
                    )
                    % order.name
                )
        return super().action_confirm()

    def _sync_opportunity_expected_revenue(self):
        leads = self.opportunity_id
        if leads:
            leads._sync_contract_expected_revenue()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders.filtered("is_contract_source")._sync_opportunity_expected_revenue()
        return orders

    def write(self, vals):
        res = super().write(vals)
        trigger = {"is_contract_source", "opportunity_id", "amount_untaxed", "order_line"}
        if trigger & set(vals.keys()):
            self._sync_opportunity_expected_revenue()
        return res

    def action_create_blanket_order(self):
        """Open the wizard that carves a Blanket Order out of this quotation."""
        self.ensure_one()
        if not self.is_contract_source:
            raise UserError(
                self.env._(
                    "Only a contract source quotation can generate Blanket "
                    "Orders. Tick 'Contract Source' first."
                )
            )
        if not self.opportunity_id:
            raise UserError(
                self.env._("Link this quotation to an Opportunity first.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("สร้างสัญญาแม่ / Create Blanket Order"),
            "res_model": "crm.blanket.order.create.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_quotation_id": self.id},
        }


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _sync_contract_source_revenue(self):
        orders = self.order_id.filtered("is_contract_source")
        orders.opportunity_id._sync_contract_expected_revenue()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._sync_contract_source_revenue()
        return lines

    def write(self, vals):
        res = super().write(vals)
        self._sync_contract_source_revenue()
        return res

    def unlink(self):
        orders = self.order_id.filtered("is_contract_source")
        res = super().unlink()
        orders.opportunity_id._sync_contract_expected_revenue()
        return res
