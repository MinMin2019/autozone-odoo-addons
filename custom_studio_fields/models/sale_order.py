# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_studio_invoicing_journal = fields.Many2one(
        'account.journal',
        string='Invoicing Journal',
        related='journal_id',
        store=False,
        copy=False,
    )
