# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockPicking(models.Model):
    _inherit = "stock.picking"

    bill_ids = fields.Many2many(
        "account.move",
        "account_move_receipt_picking_rel",
        "picking_id",
        "move_id",
        string="บิลผู้ขาย",
        copy=False,
        readonly=True,
    )
    bill_count = fields.Integer(compute="_compute_bill_count")
    purchase_bill_status = fields.Selection(
        [
            ("none", "ไม่เกี่ยวข้อง"),
            ("to_bill", "ยังไม่ตั้งหนี้"),
            ("billed", "ตั้งหนี้แล้ว"),
        ],
        string="สถานะตั้งหนี้",
        compute="_compute_purchase_bill_status",
        store=True,
        help="ใบรับสินค้าจากใบสั่งซื้อใบนี้ ออกบิลผู้ขายไปแล้วหรือยัง",
    )

    @api.depends("bill_ids")
    def _compute_bill_count(self):
        for picking in self:
            picking.bill_count = len(picking.bill_ids)

    @api.depends(
        "state",
        "bill_ids",
        "bill_ids.state",
        "move_ids.purchase_line_id",
        "move_ids.purchase_line_id.qty_invoiced",
        "move_ids.purchase_line_id.qty_received",
        "location_dest_id.usage",
    )
    def _compute_purchase_bill_status(self):
        """สถานะตั้งหนี้ของใบรับ

        "ตั้งหนี้แล้ว" ได้ 2 ทาง: (1) มีบิลที่ผูกกับใบรับนี้ผ่าน wizard ของโมดูล
        (2) บรรทัด PO ทุกบรรทัดของใบรับนี้ตั้งหนี้ครบตามที่รับแล้ว — ครอบคลุมบิลที่ออก
        ทางปุ่ม Create Bill / Auto-Complete ซึ่ง core ไม่ผูกบิลกับใบรับ ไม่งั้นใบรับเก่า
        ทั้งหมดจะค้าง "ยังไม่ตั้งหนี้" หลอกทีมบัญชี
        """
        precision = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        for picking in self:
            lines = picking._bill_receipt_lines()
            if not lines:
                picking.purchase_bill_status = "none"
            elif picking.bill_ids.filtered(lambda m: m.state != "cancel"):
                picking.purchase_bill_status = "billed"
            elif all(
                float_compare(pl.qty_invoiced, pl.qty_received, precision_digits=precision) >= 0
                for pl in lines.purchase_line_id
            ):
                picking.purchase_bill_status = "billed"
            else:
                picking.purchase_bill_status = "to_bill"

    def _bill_receipt_lines(self):
        """stock move ของใบรับนี้ที่ผูกกับบรรทัดใบสั่งซื้อ และเป็นการ "รับเข้า" จริง

        ใบคืนของผู้ขาย (ปลายทาง usage = supplier) ไม่นับ เพราะต้องออกเป็นใบลดหนี้
        ไม่ใช่บิล จึงกันออกไปตั้งแต่ต้นทางแทนที่จะปล่อยให้จำนวนติดลบ
        """
        self.ensure_one()
        if self.state != "done" or self.location_dest_id.usage == "supplier":
            return self.env["stock.move"]
        return self.move_ids.filtered(
            lambda m: m.state == "done" and m.purchase_line_id
        )

    def _bill_receipt_order(self):
        """ใบสั่งซื้อของใบรับนี้ — ต้องมีใบเดียวเท่านั้นจึงจะออกบิลอัตโนมัติได้"""
        self.ensure_one()
        orders = self._bill_receipt_lines().purchase_line_id.order_id
        if not orders:
            raise UserError(
                _("%s: ใบรับนี้ไม่ได้มาจากใบสั่งซื้อ หรือยังไม่ได้ตรวจรับ (Validate)", self.display_name)
            )
        if len(orders) > 1:
            raise UserError(
                _(
                    "%(picking)s: ใบรับนี้มีของจากใบสั่งซื้อหลายใบ (%(orders)s) "
                    "กรุณาออกบิลจากหน้าใบสั่งซื้อแทน",
                    picking=self.display_name,
                    orders=", ".join(orders.mapped("name")),
                )
            )
        return orders

    def action_create_bill_from_receipt(self):
        """เปิดหน้าต่างสร้างบิลผู้ขายตามจำนวนที่รับจริงในใบรับนี้"""
        self.ensure_one()
        order = self._bill_receipt_order()
        return self.env["purchase.bill.receipt.wizard"]._open_for(order, self)

    def action_view_receipt_bills(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "name": _("บิลผู้ขาย"),
            "context": {"create": False},
        }
        if len(self.bill_ids) == 1:
            action.update({"view_mode": "form", "res_id": self.bill_ids.id})
        else:
            action.update(
                {"view_mode": "list,form", "domain": [("id", "in", self.bill_ids.ids)]}
            )
        return action
