# -*- coding: utf-8 -*-
# ใบแจ้งหนี้ (Invoice Notice) บน Customer Invoice
#   - หัก ณ ที่จ่าย: คิดเฉพาะบรรทัด "บริการ" (product type = service หรือไม่มีสินค้า) ก่อน VAT
#     x อัตราของลูกค้า (res.partner.az_wht_percent) เมื่อลูกค้าติ๊ก az_wht_deduct และใบไม่ติ๊กซ่อน
#   - บัญชีธนาคาร: บัญชีที่ลูกค้ารายนี้โอนเข้าล่าสุด -> ถ้าไม่เคย ใช้บัญชีหลักของบริษัท (แก้ทับต่อใบได้)
#   - VAT รอรับเงิน: ถ้าภาษีบนใบเป็นแบบ cash basis (on_payment) ใบจะแสดงข้อความว่าออกใบกำกับตอนรับเงิน
# แสดงผลอย่างเดียว ไม่บันทึกบัญชี ไม่กระทบยอดลูกหนี้/การรับชำระ
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    az_notice_hide_wht = fields.Boolean(
        string="ไม่แสดงหัก ณ ที่จ่ายบนใบแจ้งหนี้", copy=False,
        help="ติ๊กเมื่อใบนี้ไม่ต้องการแสดงบรรทัดหัก ณ ที่จ่าย แม้ลูกค้าตั้งไว้ว่าหัก")
    az_notice_bank_id = fields.Many2one(
        "res.partner.bank", string="บัญชีรับโอน (ใบแจ้งหนี้)", copy=False,
        compute="_compute_az_notice_bank_id", store=True, readonly=False,
        domain=lambda self: [("partner_id", "in", self.env["res.company"].sudo().search([]).partner_id.ids)],
        help="เติมอัตโนมัติจากบัญชีที่ลูกค้าโอนเข้าล่าสุด ไม่เคยโอนใช้บัญชีหลักของบริษัท แก้เองได้")
    az_notice_promise_date = fields.Date(
        string="วันนัดรับเงิน (ใบแจ้งหนี้)", copy=False, tracking=True,
        help="มาจากใบแจ้งหนี้บนใบสั่งขายตอนออก IV ใช้เป็นวันคาดรับในรายงานคาดรับเงิน "
             "ถ้าใบวางบิลมีวันนัดรับชำระ ใช้วันในใบวางบิลแทน")
    az_notice_service_base = fields.Monetary(
        string="ค่าบริการก่อน VAT", compute="_compute_az_notice_amounts", currency_field="currency_id")
    az_notice_wht_percent = fields.Float(
        string="อัตราหัก ณ ที่จ่าย (%)", compute="_compute_az_notice_amounts", digits=(5, 2))
    az_notice_wht_amount = fields.Monetary(
        string="หัก ณ ที่จ่าย (ใบแจ้งหนี้)", compute="_compute_az_notice_amounts", currency_field="currency_id")
    az_notice_net_amount = fields.Monetary(
        string="ยอดชำระสุทธิ (ใบแจ้งหนี้)", compute="_compute_az_notice_amounts", currency_field="currency_id")
    az_notice_vat_deferred = fields.Boolean(
        string="VAT รอรับเงิน", compute="_compute_az_notice_amounts",
        help="จริงเมื่อภาษีบนใบเป็นแบบ cash basis (ออกใบกำกับภาษีตอนรับเงิน)")

    # ---------- จำนวนเงิน ----------
    @api.depends(
        "invoice_line_ids.price_subtotal", "invoice_line_ids.product_id", "invoice_line_ids.display_type",
        "invoice_line_ids.tax_ids", "amount_total", "currency_id", "az_notice_hide_wht",
        "commercial_partner_id.az_wht_deduct", "commercial_partner_id.az_wht_percent")
    def _compute_az_notice_amounts(self):
        for move in self:
            lines = move.invoice_line_ids.filtered(lambda l: l.display_type == "product")
            service_lines = lines.filtered(lambda l: not l.product_id or l.product_id.type == "service")
            base = sum(service_lines.mapped("price_subtotal"))
            partner = move.commercial_partner_id
            pct = partner.az_wht_percent if partner.az_wht_deduct else 0.0
            wht = 0.0
            if pct and base and not move.az_notice_hide_wht:
                wht = base * pct / 100.0
                wht = move.currency_id.round(wht) if move.currency_id else round(wht, 2)
            move.az_notice_service_base = base
            move.az_notice_wht_percent = pct if wht else 0.0
            move.az_notice_wht_amount = wht
            move.az_notice_net_amount = move.amount_total - wht
            move.az_notice_vat_deferred = any(
                t.tax_exigibility == "on_payment" for t in lines.mapped("tax_ids"))

    def az_notice_pct_text(self):
        self.ensure_one()
        return "%g" % (self.az_notice_wht_percent or 0.0)

    # ---------- บัญชีธนาคาร ----------
    @api.depends("partner_id", "commercial_partner_id", "company_id", "move_type")
    def _compute_az_notice_bank_id(self):
        for move in self:
            if move.move_type != "out_invoice":
                move.az_notice_bank_id = False
                continue
            move.az_notice_bank_id = move.commercial_partner_id.az_notice_last_bank(move.company_id)

    # ---------- รายงาน ----------
    def az_notice_copies(self):
        """2 ชุด: ต้นฉบับให้ลูกค้า + สำเนาเก็บบัญชี"""
        return [
            {"th": "ใบแจ้งหนี้", "en": "INVOICE", "sub": "ต้นฉบับ / ORIGINAL", "copy_type": "ลูกค้า"},
            {"th": "สำเนาใบแจ้งหนี้", "en": "INVOICE COPY", "sub": "สำเนา / COPY", "copy_type": "บัญชี"},
        ]

    def action_print_invoice_notice(self):
        return self.env.ref("custom_invoice_notice.action_report_invoice_notice").report_action(self)
