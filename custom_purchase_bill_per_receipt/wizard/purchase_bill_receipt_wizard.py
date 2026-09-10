# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class PurchaseBillReceiptWizard(models.TransientModel):
    _name = "purchase.bill.receipt.wizard"
    _description = "สร้างบิลผู้ขายจากใบรับสินค้า"

    purchase_order_id = fields.Many2one(
        "purchase.order", string="ใบสั่งซื้อ", required=True, readonly=True
    )
    company_id = fields.Many2one(related="purchase_order_id.company_id")
    currency_id = fields.Many2one(related="purchase_order_id.currency_id")
    partner_id = fields.Many2one(related="purchase_order_id.partner_id", string="ผู้ขาย")
    available_picking_ids = fields.Many2many(
        "stock.picking",
        "purchase_bill_wizard_available_picking_rel",
        compute="_compute_available_picking_ids",
    )
    picking_ids = fields.Many2many(
        "stock.picking",
        "purchase_bill_wizard_picking_rel",
        string="ใบรับสินค้า",
        required=True,
        help="ออกบิลใบเดียวต่อใบรับหนึ่งใบ หรือเลือกหลายใบเพื่อรวมเป็นบิลใบเดียวก็ได้",
    )
    line_ids = fields.One2many(
        "purchase.bill.receipt.wizard.line", "wizard_id", string="รายการ"
    )
    has_other_lines = fields.Boolean(compute="_compute_has_other_lines")
    warning_text = fields.Text(compute="_compute_warning_text")

    # ------------------------------------------------------------------
    # เปิดหน้าต่าง
    # ------------------------------------------------------------------
    @api.model
    def _open_for(self, order, pickings):
        wizard = self.create(
            {
                "purchase_order_id": order.id,
                "picking_ids": [Command.set(pickings.ids)],
            }
        )
        wizard._populate_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("สร้างบิลจากใบรับสินค้า"),
            "res_model": self._name,
            "view_mode": "form",
            "res_id": wizard.id,
            "target": "new",
        }

    # ------------------------------------------------------------------
    # compute
    # ------------------------------------------------------------------
    @api.depends("purchase_order_id")
    def _compute_available_picking_ids(self):
        for wizard in self:
            wizard.available_picking_ids = wizard.purchase_order_id.picking_ids.filtered(
                lambda p: p.purchase_bill_status in ("to_bill", "billed")
            )

    @api.depends("line_ids.source")
    def _compute_has_other_lines(self):
        for wizard in self:
            wizard.has_other_lines = bool(
                wizard.line_ids.filtered(lambda l: l.source == "other")
            )

    @api.depends("picking_ids.bill_ids", "line_ids.selected", "line_ids.source")
    def _compute_warning_text(self):
        for wizard in self:
            messages = []
            billed = wizard.picking_ids.filtered(
                lambda p: p.bill_ids.filtered(lambda m: m.state != "cancel")
            )
            if billed:
                messages.append(
                    _(
                        "ใบรับ %s เคยออกบิลไปแล้ว — ระบบตั้งจำนวนให้เฉพาะส่วนที่ยังค้าง "
                        "กรุณาตรวจสอบก่อนสร้างบิลซ้ำ",
                        ", ".join(billed.mapped("name")),
                    )
                )
            # บรรทัดที่รับของไม่ได้ (ไม่มี stock move) แต่นโยบายคุมบิลเป็น "ตามของที่รับ"
            # ถ้าตั้งหนี้ไป qty_to_invoice จะติดลบ ทำให้ใบสั่งซื้อค้าง "รอตั้งหนี้" ถาวร
            stuck = wizard.line_ids.filtered(
                lambda l: l.selected
                and l.source == "other"
                and not l.purchase_line_id.move_ids
                and l.purchase_line_id.product_id.purchase_method == "receive"
            )
            if stuck:
                messages.append(
                    _(
                        "สินค้า %s รับของไม่ได้ (ไม่มีการเคลื่อนไหวสต็อก) แต่นโยบายคุมบิลตั้งเป็น "
                        "\"ตามของที่รับ\" ถ้าตั้งหนี้ไปใบสั่งซื้อจะค้างสถานะ \"รอตั้งหนี้\" ตลอด — "
                        "ให้แก้นโยบายของสินค้าเป็น \"ตามที่สั่งซื้อ\" ก่อน",
                        ", ".join(stuck.mapped("product_id.display_name")),
                    )
                )
            wizard.warning_text = "\n".join(messages) or False

    # ------------------------------------------------------------------
    # เติมรายการ
    # ------------------------------------------------------------------
    @api.onchange("picking_ids")
    def _onchange_picking_ids(self):
        self._populate_lines()

    def _populate_lines(self):
        for wizard in self:
            wizard.line_ids = [Command.clear()] + [
                Command.create(vals) for vals in wizard._prepare_line_vals()
            ]

    def _qty_received_in_selection(self):
        """จำนวนที่รับจริงในใบรับที่เลือก แยกตามบรรทัดใบสั่งซื้อ (หน่วยของใบสั่งซื้อ)

        stock move ใช้หน่วยของตัวเองซึ่งต่างจากหน่วยในใบสั่งซื้อได้ (ในฐานปัจจุบัน
        มี move แบบนั้นอยู่ราว 1 ใน 4) จึงต้องแปลงหน่วยทุกครั้ง ห้ามใช้ตัวเลขดิบ
        """
        self.ensure_one()
        qty_by_line = defaultdict(float)
        for picking in self.picking_ids:
            for move in picking._bill_receipt_lines():
                pol = move.purchase_line_id
                if pol.order_id != self.purchase_order_id:
                    continue
                qty_by_line[pol.id] += move.product_uom._compute_quantity(
                    move.quantity, pol.product_uom
                )
        return qty_by_line

    def _prepare_line_vals(self):
        self.ensure_one()
        prec = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        qty_by_line = self._qty_received_in_selection()
        vals_list = []
        sequence = 0
        for pol in self.purchase_order_id.order_line:
            if pol.display_type:
                continue
            sequence += 10
            in_receipt = qty_by_line.get(pol.id, 0.0)
            # ตั้งหนี้ได้ไม่เกินยอดค้างของบรรทัดนั้น กันออกบิลซ้ำเมื่อใบรับใบก่อนหน้า
            # ถูกตั้งหนี้ไปแล้ว
            remaining = pol.qty_to_invoice
            base = {
                "sequence": sequence,
                "purchase_line_id": pol.id,
                "name": pol.name,
                "product_id": pol.product_id.id,
                "product_uom_id": pol.product_uom.id,
                "price_unit": pol.price_unit,
                "qty_receipt": in_receipt,
                "qty_pending": remaining,
            }
            if float_compare(in_receipt, 0.0, precision_digits=prec) > 0:
                qty = min(in_receipt, max(remaining, 0.0))
                base.update(
                    {
                        "source": "receipt",
                        "qty": qty,
                        "selected": float_compare(qty, 0.0, precision_digits=prec) > 0,
                    }
                )
                vals_list.append(base)
                continue
            # บรรทัดที่ไม่ได้อยู่ในใบรับที่เลือก — เสนอให้ติ๊กพ่วงได้
            extra = pol._bill_receipt_extra_qty()
            other_qty = remaining if remaining > 0 else extra
            if float_compare(other_qty, 0.0, precision_digits=prec) <= 0:
                continue
            base.update(
                {
                    "source": "other",
                    "qty": other_qty,
                    "qty_pending": other_qty,
                    "selected": False,
                }
            )
            vals_list.append(base)
        return vals_list

    # ------------------------------------------------------------------
    # สร้างบิล
    # ------------------------------------------------------------------
    def action_generate_bill(self):
        self.ensure_one()
        prec = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        lines = self.line_ids.filtered(
            lambda l: l.selected
            and float_compare(l.qty, 0.0, precision_digits=prec) > 0
        )
        if not lines:
            raise UserError(
                _("ยังไม่ได้เลือกรายการใดเลย หรือจำนวนที่เลือกเป็นศูนย์ทั้งหมด")
            )

        order = self.purchase_order_id.with_company(self.purchase_order_id.company_id)
        # ใช้ _prepare_invoice ของ Odoo เพื่อให้สมุดรายวัน/เงื่อนไขชำระ/เลข PO
        # (จากโมดูล thai_accounting_vouchers) ถูกเซ็ตเหมือนปุ่ม Create Bill ปกติ
        invoice_vals = order._prepare_invoice()
        invoice_vals["invoice_line_ids"] = []
        sequence = 10
        for wline in lines:
            line_vals = wline.purchase_line_id._prepare_account_move_line()
            line_vals.update({"quantity": wline.qty, "sequence": sequence})
            invoice_vals["invoice_line_ids"].append(Command.create(line_vals))
            sequence += 10
        invoice_vals["receipt_picking_ids"] = [Command.set(self.picking_ids.ids)]

        move = (
            self.env["account.move"]
            .with_company(order.company_id)
            .with_context(default_move_type="in_invoice")
            .create(invoice_vals)
        )

        picking_names = ", ".join(self.picking_ids.mapped("name"))
        move.message_post(
            body=_(
                "ตั้งหนี้ตามใบรับสินค้า %(pickings)s ของ %(order)s",
                pickings=picking_names,
                order=order.name,
            )
        )
        for picking in self.picking_ids:
            picking.message_post(
                body=_("สร้างบิลผู้ขาย %s จากใบรับนี้", move.name or _("ฉบับร่าง"))
            )

        return {
            "type": "ir.actions.act_window",
            "name": _("บิลผู้ขาย"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": move.id,
        }


class PurchaseBillReceiptWizardLine(models.TransientModel):
    _name = "purchase.bill.receipt.wizard.line"
    _description = "รายการที่จะตั้งหนี้จากใบรับสินค้า"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        "purchase.bill.receipt.wizard", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(default=10)
    purchase_line_id = fields.Many2one(
        "purchase.order.line", string="บรรทัดใบสั่งซื้อ", required=True, readonly=True
    )
    source = fields.Selection(
        [
            ("receipt", "ในใบรับที่เลือก"),
            ("other", "ค้างตั้งหนี้ (ไม่ได้อยู่ในใบรับนี้)"),
        ],
        string="ที่มา",
        required=True,
        readonly=True,
    )
    selected = fields.Boolean(string="เลือก")
    name = fields.Char(string="รายละเอียด", readonly=True)
    product_id = fields.Many2one("product.product", string="สินค้า", readonly=True)
    product_uom_id = fields.Many2one("uom.uom", string="หน่วย", readonly=True)
    qty_receipt = fields.Float(
        string="รับในใบนี้", digits="Product Unit of Measure", readonly=True
    )
    qty_pending = fields.Float(
        string="ค้างตั้งหนี้", digits="Product Unit of Measure", readonly=True
    )
    qty = fields.Float(string="จำนวนที่ตั้งหนี้", digits="Product Unit of Measure")
    price_unit = fields.Float(string="ราคา/หน่วย", digits="Product Price", readonly=True)
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    price_subtotal = fields.Monetary(
        string="ยอดรวม", compute="_compute_price_subtotal", currency_field="currency_id"
    )

    @api.depends("qty", "price_unit", "purchase_line_id.discount")
    def _compute_price_subtotal(self):
        for line in self:
            discount = line.purchase_line_id.discount or 0.0
            line.price_subtotal = line.qty * line.price_unit * (1 - discount / 100.0)

    @api.onchange("qty")
    def _onchange_qty(self):
        prec = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        for line in self:
            if not float_is_zero(line.qty, precision_digits=prec):
                line.selected = True
