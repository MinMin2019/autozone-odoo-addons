# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.tools import SQL


class PurchaseReport(models.Model):
    _inherit = "purchase.report"

    az_branch_id = fields.Many2one("account.analytic.account", "สาขา", readonly=True)

    def _select(self) -> SQL:
        return SQL("%s, l.az_branch_id as az_branch_id", super()._select())

    def _group_by(self) -> SQL:
        return SQL("%s, l.az_branch_id", super()._group_by())
