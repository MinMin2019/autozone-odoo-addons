# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    loan_ids = fields.One2many('hr.employee.loan', 'employee_id', string='เงินกู้')
    loan_count = fields.Integer(compute='_compute_loan_count')

    def _compute_loan_count(self):
        counts = dict(self.env['hr.employee.loan']._read_group(
            [('employee_id', 'in', self.ids), ('state', '!=', 'cancel')],
            ['employee_id'], ['__count']))
        for employee in self:
            employee.loan_count = counts.get(employee, 0)

    def action_view_loans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'เงินกู้พนักงาน',
            'res_model': 'hr.employee.loan',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
