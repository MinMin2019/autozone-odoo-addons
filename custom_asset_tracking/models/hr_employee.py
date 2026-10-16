# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.osv import expression

# ใส่ใน context ของช่อง Custodian เท่านั้น — ไม่เปลี่ยนการค้นหาพนักงานที่อื่นในระบบ
CODE_SEARCH_CONTEXT = 'az_employee_code_search'


def _add_code_search(model, domain, operator, value):
    """เพิ่มเงื่อนไขค้นด้วยรหัสพนักงาน (registration_number)
    ฟิลด์นี้จำกัดกลุ่ม HR → ค้นแบบ sudo แล้วคืนเป็น id (ไม่ได้อ่านข้อมูลอื่นของพนักงาน)"""
    if (model.env.context.get(CODE_SEARCH_CONTEXT)
            and operator in ('ilike', '=ilike', 'like', '=like', '=')
            and isinstance(value, str) and value.strip()):
        employees = model.env['hr.employee'].sudo().search([('registration_number', operator, value.strip())])
        if employees:
            domain = expression.OR([domain, [('id', 'in', employees.ids)]])
    return domain


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    @api.model
    def _search_display_name(self, operator, value):
        return _add_code_search(self, super()._search_display_name(operator, value), operator, value)

    @api.depends_context(CODE_SEARCH_CONTEXT)
    def _compute_display_name(self):
        super()._compute_display_name()
        if not self.env.context.get(CODE_SEARCH_CONTEXT):
            return
        # แสดง "[รหัส] ชื่อ" ในช่อง Custodian เพื่อแยกคนชื่อซ้ำ
        codes = {emp.id: emp.registration_number for emp in self.sudo()}
        for employee in self:
            code = codes.get(employee.id)
            if code:
                employee.display_name = f'[{code}] {employee.display_name}'


class HrEmployeePublic(models.Model):
    # user ที่ไม่มีสิทธิ์ HR ค้นพนักงานผ่าน hr.employee.public (hr.employee ส่งต่อให้) → ต้องเพิ่มที่นี่ด้วย
    _inherit = 'hr.employee.public'

    @api.model
    def _search_display_name(self, operator, value):
        return _add_code_search(self, super()._search_display_name(operator, value), operator, value)
