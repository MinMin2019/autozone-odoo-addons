# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployeeLoanReport(models.Model):
    """แถวรายงานเงินกู้ประจำเดือน — สร้างใหม่ทุกครั้งที่กดดูรายงาน (แยกตามผู้ใช้)

    เก็บเป็นตารางจริงแทน SQL view เพราะยอดยกมา/คงเหลือขึ้นกับเดือนที่เลือก
    """
    _name = 'hr.employee.loan.report'
    _description = 'Employee Loan Monthly Report (รายงานเงินกู้ประจำเดือน)'
    _order = 'registration_number, loan_name'

    date_from = fields.Date(string='ตั้งแต่', readonly=True)
    date_to = fields.Date(string='ถึง', readonly=True)
    loan_id = fields.Many2one('hr.employee.loan', string='สัญญา', readonly=True,
                              ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='ชื่อพนักงาน', readonly=True)
    # เก็บค่าเป็นข้อความ ไม่ทำ related — ฟิลด์ต้นทางติด groups HR (ดู registration_number ใน loan)
    registration_number = fields.Char(string='รหัสพนักงาน', readonly=True)
    department_id = fields.Many2one('hr.department', string='แผนก', readonly=True)
    loan_name = fields.Char(string='เลขที่สัญญา', readonly=True)
    date_loan = fields.Date(string='วันที่จ่าย (ค.ศ.)', readonly=True)
    date_loan_be = fields.Char(string='วันที่จ่าย', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)

    principal_amount = fields.Float(digits=(16, 2), string='เงินต้นตามสัญญา', readonly=True)
    interest_total = fields.Float(digits=(16, 2), string='ดอกเบี้ยตามสัญญา', readonly=True)
    opening_principal = fields.Float(digits=(16, 2), string='ยกมาต้นเดือน', readonly=True)
    new_loan_amount = fields.Float(
        string='จ่ายเพิ่ม', digits=(16, 2), readonly=True,
        help="เงินกู้ที่จ่ายให้พนักงานในเดือนนี้ (กู้เพิ่ม = สัญญาใหม่)")
    paid_principal = fields.Float(
        string='หักเงินต้น', digits=(16, 2), readonly=True,
        help="งวดที่ครบกำหนดในเดือนนี้และตัดแล้ว + งวดที่พนักงานโปะล่วงหน้าในเดือนนี้")
    paid_interest = fields.Float(digits=(16, 2), string='หักดอกเบี้ย', readonly=True)
    remaining_principal = fields.Float(digits=(16, 2), string='คงเหลือเงินต้น', readonly=True)
    remaining_interest = fields.Float(digits=(16, 2), string='คงเหลือดอกเบี้ย', readonly=True)
    remaining_total = fields.Float(digits=(16, 2), string='รวมคงเหลือ', readonly=True)
    count_remaining = fields.Integer(string='งวดคงเหลือ', readonly=True)
    count_overdue = fields.Integer(
        string='งวดค้าง', readonly=True,
        help="งวดที่เลยกำหนดหักแล้ว (ภายในสิ้นเดือนนี้) แต่ยังไม่ตัด (รอหัก/อยู่ในสลิปที่ยังไม่ Validate)")
    status = fields.Selection([
        ('running', 'กำลังผ่อน'),
        ('done', 'ปิดยอดแล้ว'),
    ], string='สถานะ', readonly=True)
