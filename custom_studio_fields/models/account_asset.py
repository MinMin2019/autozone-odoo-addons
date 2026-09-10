# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    # ชื่อฟิลด์ต้องคง x_studio_* เดิมไว้ ให้ตรงกับคอลัมน์ใน DB และ
    # custom_asset_report_code ที่อ้าง x_studio_asset_code อยู่
    x_studio_asset_code = fields.Char(string='Asset Code')
    x_studio_location = fields.Char(string='Location')
