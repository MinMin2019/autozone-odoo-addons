# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    az_notice_default_bank_id = fields.Many2one(
        "res.partner.bank", string="บัญชีรับโอนหลัก (ใบแจ้งหนี้)",
        domain="[('partner_id', '=', partner_id)]",
        help="บัญชีที่พิมพ์บนใบแจ้งหนี้เมื่อลูกค้ารายนั้นยังไม่เคยโอนเงินเข้าบัญชีไหนมาก่อน")
