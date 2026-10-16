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
    custodian_code = fields.Char(
        string='Custodian Code',
        compute='_compute_custodian_code',
        search='_search_custodian_code',
        help='รหัสพนักงานของผู้ถือครอง (ใช้ค้นหาในลิสต์)',
    )

    main_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Main Analytic',
        compute='_compute_main_analytic_account_id',
        store=True,
        index='btree_not_null',
        help='Analytic ที่มีสัดส่วนสูงสุดใน Analytic Distribution ใช้จัดกลุ่ม/ค้นหาในลิสต์',
    )
    main_analytic_plan_id = fields.Many2one(
        related='main_analytic_account_id.plan_id',
        string='Main Analytic Plan',
        store=True,
    )

    @api.depends('custodian_id')
    def _compute_custodian_code(self):
        # registration_number จำกัดกลุ่ม HR → อ่านแบบ sudo เฉพาะรหัส
        for asset in self:
            asset.custodian_code = asset.custodian_id.sudo().registration_number or False

    def _search_custodian_code(self, operator, value):
        if operator not in ('ilike', '=ilike', 'like', '=like', '=') or not value:
            return [('id', 'in', [])]  # ไม่รองรับ operator อื่น → ไม่พบ
        employees = self.env['hr.employee'].sudo().with_context(active_test=False).search(
            [('registration_number', operator, value)])
        return [('custodian_id', 'in', employees.ids)]

    @api.depends('analytic_distribution')
    def _compute_main_analytic_account_id(self):
        # Group by ตรง ๆ จาก analytic_distribution (JSON) ไม่ได้ → เลือกตัวที่ % สูงสุด
        # key อาจเป็น "54" หรือ "3,54" (ข้าม plan) → ใช้ account ตัวแรกของ key
        for asset in self:
            distribution = asset.analytic_distribution or {}
            account_id = False
            if distribution:
                key = max(distribution, key=lambda k: distribution[k] or 0)
                account_id = int(key.split(',')[0])
            asset.main_analytic_account_id = self.env['account.analytic.account'].browse(account_id).exists()

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        # คอลัมน์ Class (x_class_id) มาจาก Studio ซ้ำกับ Analytic Distribution → ซ่อนในลิสต์
        # ทำใน Python เพราะ view ของ Studio โหลดหลังโมดูลนี้ xpath ใน XML หาไม่เจอตอนอัปเกรด
        if view_type == 'list':
            for node in arch.xpath("//field[@name='x_class_id']"):
                node.set('column_invisible', '1')
        return arch, view
