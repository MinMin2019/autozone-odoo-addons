# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    custodian_id = fields.Many2one(
        'hr.employee',
        string='Custodian',
        tracking=True,
        index='btree_not_null',
        help='พนักงานผู้ถือครอง/รับผิดชอบทรัพย์สินชิ้นนี้',
    )

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        # คอลัมน์ Class (x_class_id) มาจาก Studio ซ้ำกับ Analytic Distribution → ซ่อนในลิสต์
        # ทำใน Python เพราะ view ของ Studio โหลดหลังโมดูลนี้ xpath ใน XML หาไม่เจอตอนอัปเกรด
        if view_type == 'list':
            for node in arch.xpath("//field[@name='x_class_id']"):
                node.set('column_invisible', '1')
        return arch, view
