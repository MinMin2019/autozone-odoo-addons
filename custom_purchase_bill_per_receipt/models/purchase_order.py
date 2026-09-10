# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    billable_picking_count = fields.Integer(
        string="ใบรับที่ยังไม่ตั้งหนี้",
        compute="_compute_billable_picking_count",
    )

    @api.depends("picking_ids.purchase_bill_status")
    def _compute_billable_picking_count(self):
        for order in self:
            order.billable_picking_count = len(order._billable_pickings())

    def _billable_pickings(self):
        """ใบรับสินค้าของใบสั่งซื้อนี้ที่ตรวจรับแล้วและยังไม่ได้ออกบิล"""
        self.ensure_one()
        return self.picking_ids.filtered(
            lambda p: p.purchase_bill_status == "to_bill"
        )

    def action_open_bill_per_receipt(self):
        """เปิดหน้าต่างเลือกใบรับสินค้าที่ต้องการออกบิล (ออกได้ทีละใบ หรือหลายใบรวมกัน)"""
        self.ensure_one()
        if self.state not in ("purchase", "done"):
            raise UserError(_("ใบสั่งซื้อต้องอยู่สถานะยืนยันแล้ว จึงจะออกบิลได้"))
        pickings = self._billable_pickings()
        if not pickings:
            raise UserError(
                _(
                    "%s: ไม่มีใบรับสินค้าที่ตรวจรับแล้วและยังไม่ได้ออกบิล",
                    self.display_name,
                )
            )
        return self.env["purchase.bill.receipt.wizard"]._open_for(
            self, pickings[:1] if len(pickings) > 1 else pickings
        )


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def _bill_receipt_extra_qty(self):
        """จำนวนค้างของบรรทัดที่ไม่มีการเคลื่อนไหวสต็อกเลย (ค่าขนส่ง/ค่าบริการ)

        บรรทัดพวกนี้ qty_received เป็น 0 ตลอดไป ถ้านโยบายควบคุมบิลเป็น
        "ตามของที่รับ" ปุ่ม Create Bill มาตรฐานจะข้ามทิ้ง ทำให้ใบสั่งซื้อค้าง
        สถานะ "รอตั้งหนี้" ถาวร จึงเปิดให้ติ๊กพ่วงเข้าบิลได้เอง
        """
        self.ensure_one()
        if self.display_type or self.move_ids:
            return 0.0
        return self.product_qty - self.qty_invoiced
