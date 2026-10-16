# -*- coding: utf-8 -*-
# ตั้งต่อลูกค้า: รายนี้หักภาษี ณ ที่จ่ายไหม + กี่ %
# ค่าเริ่มต้น: นิติบุคคล (is_company) = หัก 3%, บุคคล = ไม่หัก  แก้ทับได้ที่การ์ดลูกค้า
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    az_wht_deduct = fields.Boolean(
        string="ลูกค้าหักภาษี ณ ที่จ่าย",
        compute="_compute_az_wht_deduct", store=True, readonly=False,
        help="ติ๊ก = ใบแจ้งหนี้จะแสดงบรรทัดหัก ณ ที่จ่าย (คิดจากค่าบริการก่อน VAT) "
             "และยอดชำระสุทธิหลังหัก  ค่าเริ่มต้น: นิติบุคคลติ๊กไว้ บุคคลธรรมดาไม่ติ๊ก")
    az_wht_percent = fields.Float(
        string="อัตราหัก ณ ที่จ่าย (%)", default=3.0, digits=(5, 2))

    @api.depends("is_company")
    def _compute_az_wht_deduct(self):
        for p in self:
            p.az_wht_deduct = bool(p.is_company)

    def az_notice_last_bank(self, company):
        """บัญชีบริษัทที่ลูกค้ารายนี้โอนเข้าล่าสุด (ใบรับเงิน inbound ที่ยืนยันแล้ว) -> ไม่เคย = บัญชีหลักของบริษัท"""
        bank = self.env["res.partner.bank"]
        if self:
            pay = self.env["account.payment"].sudo().search([
                ("partner_id", "child_of", self.commercial_partner_id.id),
                ("payment_type", "=", "inbound"),
                ("partner_type", "=", "customer"),
                ("state", "in", ("in_process", "paid")),
                ("journal_id.type", "=", "bank"),
                ("journal_id.bank_account_id", "!=", False),
                ("company_id", "=", company.id),
            ], order="date desc, id desc", limit=1)
            bank = pay.journal_id.bank_account_id
        return bank or company.az_notice_default_bank_id
