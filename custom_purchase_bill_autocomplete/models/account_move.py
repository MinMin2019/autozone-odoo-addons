# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.tools import float_is_zero


class AccountMove(models.Model):
    _inherit = "account.move"

    def _add_purchase_order_lines(self, purchase_order_lines):
        """กรองบรรทัดที่ไม่มีอะไรให้ตั้งหนี้ออกก่อนดึงเข้าบิล

        core ของ Auto-Complete (purchase/models/account_invoice.py) วนทุกบรรทัดของ PO
        ไม่กรอง qty_to_invoice = 0 ต่างจากปุ่ม Create Bill บนหน้า PO
        (purchase_order.py action_create_invoice) ทำให้บัญชีต้องมานั่งลบบรรทัด 0 เอง
        โมดูลนี้ใช้กติกาเดียวกับ Create Bill: ข้ามบรรทัด 0 และคง Section ไว้เฉพาะที่มีบรรทัดจริงตามหลัง
        """
        precision = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        keep = self.env["purchase.order.line"]
        pending_section = None
        for line in purchase_order_lines:
            if line.display_type == "line_section":
                pending_section = line
                continue
            if line.display_type == "line_note":
                continue
            if float_is_zero(line.qty_to_invoice, precision_digits=precision):
                continue
            if pending_section:
                keep |= pending_section
                pending_section = None
            keep |= line
        return super()._add_purchase_order_lines(keep)

    @api.onchange("purchase_vendor_bill_id", "purchase_id")
    def _onchange_purchase_auto_complete(self):
        """เตือนเมื่อเลือก PO แล้วไม่มีบรรทัดไหนถูกดึงเข้าบิลเลย

        กรณีที่เจอบ่อย: PO ยังไม่ได้ตรวจรับของ (qty_received = 0) หรือตั้งหนี้ครบไปแล้ว
        core จะปล่อยให้บิลว่างเงียบ ๆ ทำให้บัญชีเข้าใจว่าระบบพัง
        """
        order = self.purchase_vendor_bill_id.purchase_order_id or self.purchase_id
        lines_before = self.invoice_line_ids
        res = super()._onchange_purchase_auto_complete()
        if order and not (self.invoice_line_ids - lines_before):
            warning = {
                "title": _("ไม่มีรายการให้ตั้งหนี้"),
                "message": _(
                    "ใบสั่งซื้อ %s ยังไม่มีบรรทัดที่ตั้งหนี้ได้\n"
                    "สาเหตุที่พบบ่อย: คลังยังไม่ได้ตรวจรับของ (Validate ใบรับ) "
                    "หรือใบสั่งซื้อนี้ตั้งหนี้ครบแล้ว",
                    order.name,
                ),
            }
            if isinstance(res, dict):
                res = dict(res, warning=warning)
            else:
                res = {"warning": warning}
        return res
