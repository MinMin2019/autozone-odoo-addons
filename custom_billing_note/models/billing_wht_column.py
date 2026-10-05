# -*- coding: utf-8 -*-
# v18.0.1.8.4 คอลัมน์ "หัก 3%" / "หลังหัก 3%" ในตารางใบแจ้งหนี้บนฟอร์มใบวางบิล
# ต่อใบ: หัก 3% = ยอดก่อน VAT x 3% (หัก ณ ที่จ่ายคิดจากยอดก่อน VAT ตามปกติ)
#        หลังหัก 3% = ยอดรวม VAT - หัก 3%
# ใช้แสดงผลอย่างเดียว ไม่บันทึกบัญชี / ไม่กระทบยอดรวมวางบิลและการรับชำระเงิน
from odoo import api, fields, models

BN_WHT_PERCENT = 3.0


class AccountMove(models.Model):
    _inherit = 'account.move'

    bn_wht_amount = fields.Monetary(
        string='หัก 3%', compute='_compute_bn_amount_after_wht',
        currency_field='currency_id',
        help='ภาษีหัก ณ ที่จ่าย 3% ของยอดก่อน VAT (แสดงผลบนใบวางบิลเท่านั้น)')
    bn_amount_after_wht = fields.Monetary(
        string='หลังหัก 3%', compute='_compute_bn_amount_after_wht',
        currency_field='currency_id',
        help='ยอดรวม VAT หักภาษี ณ ที่จ่าย 3% ของยอดก่อน VAT (แสดงผลบนใบวางบิลเท่านั้น)')

    @api.depends('amount_total', 'amount_untaxed', 'currency_id')
    def _compute_bn_amount_after_wht(self):
        for move in self:
            wht = move.amount_untaxed * BN_WHT_PERCENT / 100.0
            wht = move.currency_id.round(wht) if move.currency_id else round(wht, 2)
            move.bn_wht_amount = wht
            move.bn_amount_after_wht = move.amount_total - wht


class CustomerBillingNote(models.Model):
    _inherit = 'customer.billing.note'

    amount_wht = fields.Monetary(string='หัก 3%', compute='_compute_amount_after_wht')
    amount_after_wht = fields.Monetary(string='ยอดหลังหัก 3%', compute='_compute_amount_after_wht')

    @api.depends('invoice_ids.amount_total', 'invoice_ids.amount_untaxed')
    def _compute_amount_after_wht(self):
        for rec in self:
            rec.amount_wht = sum(rec.invoice_ids.mapped('bn_wht_amount'))
            rec.amount_after_wht = sum(rec.invoice_ids.mapped('bn_amount_after_wht'))
