# -*- coding: utf-8 -*-
# ชื่อสาขาธนาคาร (Odoo ไม่มีช่องนี้) ใช้พิมพ์ในกล่อง "ช่องทางการชำระเงิน" บนใบแจ้งหนี้
from odoo import fields, models


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    az_branch_name = fields.Char(string="สาขาธนาคาร")
