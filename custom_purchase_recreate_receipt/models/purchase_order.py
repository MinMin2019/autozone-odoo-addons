# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    can_recreate_receipt = fields.Boolean(
        string="Can Recreate Receipt",
        compute="_compute_can_recreate_receipt",
        help="ใบรับสินค้าของใบสั่งซื้อนี้ถูกยกเลิกไปหมดแล้ว แต่ยังมีสินค้าค้างรับอยู่",
    )

    @api.depends(
        "state",
        "picking_ids",
        "picking_ids.state",
        "order_line.product_qty",
        "order_line.product_id",
        "order_line.move_ids.state",
        "order_line.move_ids.product_uom_qty",
    )
    def _compute_can_recreate_receipt(self):
        for order in self:
            order.can_recreate_receipt = not order._recreate_receipt_blocker()

    def _get_receipt_pending_lines(self):
        """บรรทัดสินค้าที่ยังไม่มี stock move รองรับครบตามจำนวนสั่งซื้อ

        นับด้วยตรรกะเดียวกับที่ Odoo ใช้ตอนยืนยัน PO (`_get_qty_procurement`)
        ซึ่งไม่นับ move ที่ถูกยกเลิก จำนวนค้างจึงเท่ากับที่ระบบจะสร้างให้เอง
        """
        self.ensure_one()
        pending = self.env["purchase.order.line"]
        for line in self.order_line:
            if line.display_type or line.product_id.type != "consu":
                continue
            rounding = line.product_uom.rounding or 0.01
            if float_compare(
                line._get_qty_procurement(),
                line.product_qty,
                precision_rounding=rounding,
            ) < 0:
                pending |= line
        return pending

    def _recreate_receipt_blocker(self):
        """คืนข้อความเหตุผลที่สร้างใบรับใหม่ไม่ได้ หรือ False ถ้าสร้างได้"""
        self.ensure_one()
        if self.state not in ("purchase", "done"):
            return _("ใบสั่งซื้อต้องอยู่สถานะยืนยันแล้ว จึงจะสร้างใบรับสินค้าได้")
        if self.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
            return _(
                "ใบสั่งซื้อนี้ยังมีใบรับสินค้าที่ใช้งานอยู่ ให้ไปรับของจากใบเดิม"
            )
        if not self.picking_ids.filtered(lambda p: p.state == "cancel"):
            # กันไม่ให้ปุ่มไปโผล่กับใบที่จงใจไม่รับของส่วนที่เหลือ (ปฏิเสธ backorder)
            return _("ใบสั่งซื้อนี้ไม่มีใบรับสินค้าที่ถูกยกเลิก")
        if not self._get_receipt_pending_lines():
            return _("ใบสั่งซื้อนี้รับสินค้าครบแล้ว ไม่มีของค้างรับ")
        return False

    def action_recreate_receipt(self):
        """สร้างใบรับสินค้าใหม่ตามจำนวนที่ยังค้าง หลังใบรับเดิมถูกยกเลิก

        Odoo ถือว่าใบรับที่ถูกยกเลิก = จบเรื่องรับของแล้ว (`_compute_is_shipped`
        นับ cancel เท่ากับ done) ปุ่ม Receive Products จึงหายไปและระบบไม่สร้าง
        ใบรับใหม่ให้เอง เมธอดนี้เรียก `_create_picking()` ซ้ำ ซึ่งจะข้ามใบรับที่
        done/cancel แล้วออกใบใหม่ให้เฉพาะจำนวนที่ยังค้าง
        """
        for order in self:
            blocker = order._recreate_receipt_blocker()
            if blocker:
                raise UserError(_("%(order)s: %(reason)s", order=order.display_name, reason=blocker))

        pickings_before = self.picking_ids
        self._create_picking()

        for order in self:
            new_pickings = order.picking_ids - pickings_before
            if not new_pickings:
                raise UserError(
                    _(
                        "%s: สร้างใบรับสินค้าใหม่ไม่สำเร็จ กรุณาตรวจสอบประเภทการดำเนินการ (Deliver To) ของใบสั่งซื้อ",
                        order.display_name,
                    )
                )
            order.message_post(
                body=_(
                    "สร้างใบรับสินค้าใหม่ %s เนื่องจากใบรับเดิมถูกยกเลิก",
                    ", ".join(new_pickings.mapped("name")),
                )
            )

        if len(self) == 1:
            return self.action_view_picking()
        return True
