# -*- coding: utf-8 -*-
from odoo import fields, models


class AzAssetImage(models.Model):
    """รูปเพิ่มเติมของทรัพย์สิน (รูปหลักยังใช้ image_1920 บน account.asset เหมือนเดิม)"""
    _name = 'az.asset.image'
    _description = 'Asset Additional Image'
    _inherit = ['image.mixin']
    _order = 'sequence, id'

    asset_id = fields.Many2one(
        'account.asset', string='Asset',
        required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Caption', help='คำอธิบายรูป เช่น ด้านหน้า, ป้ายทะเบียน, รอยชำรุด')


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    az_image_ids = fields.One2many(
        'az.asset.image', 'asset_id', string='Additional Images',
    )
