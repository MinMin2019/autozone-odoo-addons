# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayslipInput(models.Model):
    _inherit = 'hr.payslip.input'

    # ธงระบุว่ารายการนี้มาจากการ import ไฟล์ — ใช้แยกจากรายการที่ HR กรอกมือ
    # เพื่อให้การ import ซ้ำล้างเฉพาะของที่มาจากไฟล์ (โหมด Replace ทั้งก้อน)
    is_imported = fields.Boolean(string='Imported from File', copy=False)
