# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

THAI_MONTHS = [
    ('1', 'มกราคม'), ('2', 'กุมภาพันธ์'), ('3', 'มีนาคม'), ('4', 'เมษายน'),
    ('5', 'พฤษภาคม'), ('6', 'มิถุนายน'), ('7', 'กรกฎาคม'), ('8', 'สิงหาคม'),
    ('9', 'กันยายน'), ('10', 'ตุลาคม'), ('11', 'พฤศจิกายน'), ('12', 'ธันวาคม'),
]


class HrEmployeeLoanReportWizard(models.TransientModel):
    _name = 'hr.employee.loan.report.wizard'
    _description = 'Employee Loan Monthly Report Wizard'

    month = fields.Selection(
        THAI_MONTHS, string='เดือน', required=True,
        default=lambda self: str(fields.Date.context_today(self).month))
    year_be = fields.Integer(
        string='ปี (พ.ศ.)', required=True,
        default=lambda self: fields.Date.context_today(self).year + 543)

    def _month_range(self):
        start = fields.Date.to_date('%04d-%02d-01' % (self.year_be - 543, int(self.month)))
        return start, start + relativedelta(months=1, days=-1)

    @api.model
    def _loan_row(self, loan, start, end):
        """ยอดของสัญญาเดียวในเดือน [start, end] — คืน None ถ้าไม่มียอดยกมาและไม่เคลื่อนไหว"""
        # จ่ายเพิ่ม = เงินกู้ที่จ่ายให้พนักงานในเดือนนี้ (กู้เพิ่ม = เปิดสัญญาใหม่เสมอ)
        # สัญญาที่จ่ายในเดือนนี้จึงยกมา 0 แล้วยอดไปขึ้นช่องจ่ายเพิ่มแทน
        if start <= loan.date_loan <= end:
            opening, new_loan = 0.0, loan.principal_amount
        else:
            opening, new_loan = loan.principal_amount, 0.0
        paid = paid_int = rem_int = 0.0
        count_rem = count_overdue = 0
        # งวดค้าง = เลยวันกำหนดหักแล้ว — เดือนปัจจุบันงวดที่ยังไม่ถึงวันหักไม่นับ
        overdue_before = min(end + relativedelta(days=1), fields.Date.context_today(self))
        for line in loan.line_ids:
            pay_date, is_prepaid = line._settle_info()
            if pay_date:
                # เดือนที่นับยอด: โปะล่วงหน้า = เดือนที่ชำระ, ปกติ = เดือนกำหนดหัก
                # (โปะรวมอยู่ในหักเงินต้นของเดือนที่ชำระ)
                month_of = (pay_date if is_prepaid else line.date_due).replace(day=1)
                if month_of < start:
                    opening -= line.amount
                    continue
                if month_of == start:
                    paid += line.amount
                    paid_int += line.amount_interest
                    continue
            # ยังไม่ตัด ณ สิ้นเดือนนี้
            rem_int += line.amount_interest
            count_rem += 1
            if not pay_date and line.date_due < overdue_before:
                count_overdue += 1

        currency = loan.currency_id
        if currency.is_zero(opening) and currency.is_zero(new_loan + paid + paid_int):
            return None
        remaining = opening + new_loan - paid
        return {
            'date_from': start,
            'date_to': end,
            'loan_id': loan.id,
            'employee_id': loan.employee_id.id,
            'registration_number': loan.registration_number,
            'department_id': loan.department_id.id,
            'loan_name': loan.name,
            'date_loan': loan.date_loan,
            'date_loan_be': '%s/%d' % (loan.date_loan.strftime('%d/%m'), loan.date_loan.year + 543),
            'company_id': loan.company_id.id,
            'currency_id': currency.id,
            'principal_amount': loan.principal_amount,
            'interest_total': loan.interest_total,
            'opening_principal': opening,
            'new_loan_amount': new_loan,
            'paid_principal': paid,
            'paid_interest': paid_int,
            'remaining_principal': remaining,
            'remaining_interest': rem_int,
            'remaining_total': remaining + rem_int,
            'count_remaining': count_rem,
            'count_overdue': count_overdue,
            'status': 'done' if currency.compare_amounts(remaining, 0) <= 0 else 'running',
        }

    def action_view_report(self):
        self.ensure_one()
        start, end = self._month_range()
        Report = self.env['hr.employee.loan.report']
        Report.search([('create_uid', '=', self.env.uid)]).unlink()

        loans = self.env['hr.employee.loan'].search([
            ('state', 'in', ('running', 'done')),
            ('company_id', 'in', self.env.companies.ids),
        ])
        vals_list = []
        for loan in loans:
            # วันเริ่มสัญญาใช้ค่าที่เร็วกว่าระหว่างวันจ่ายกับงวดแรก กันกรณีกรอกปีวันจ่ายผิด
            if min(loan.date_loan, loan.date_first_due) > end:
                continue
            row = self._loan_row(loan, start, end)
            if row:
                vals_list.append(row)
        Report.create(vals_list)

        label = '%s %s' % (dict(THAI_MONTHS)[self.month], self.year_be)
        action = self.env['ir.actions.act_window']._for_xml_id(
            'custom_hr_loan.action_hr_employee_loan_report')
        action['name'] = 'รายงานเงินกู้ประจำเดือน %s' % label
        action['domain'] = [('create_uid', '=', self.env.uid)]
        return action
