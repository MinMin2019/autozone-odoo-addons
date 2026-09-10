# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_vendor = fields.Boolean(
        string='Is a Vendor',
        compute='_compute_is_vendor',
        inverse='_inverse_is_vendor',
        search='_search_is_vendor',
        help='ติ๊กเพื่อให้ contact รายนี้แสดงในช่อง Vendor ของใบสั่งซื้อ',
    )

    @api.depends('supplier_rank')
    def _compute_is_vendor(self):
        for partner in self:
            partner.is_vendor = partner.supplier_rank > 0

    def _inverse_is_vendor(self):
        for partner in self:
            if partner.is_vendor and partner.supplier_rank <= 0:
                partner.supplier_rank = 1
            elif not partner.is_vendor and partner.supplier_rank > 0:
                partner.supplier_rank = 0

    def _search_is_vendor(self, operator, value):
        if operator not in ('=', '!='):
            raise NotImplementedError('Unsupported operator on is_vendor')
        is_set = (operator == '=') == bool(value)
        return [('supplier_rank', '>' if is_set else '<=', 0)]
