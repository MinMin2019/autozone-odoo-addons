# -*- coding: utf-8 -*-
"""สร้าง/อัปเดตสัญญาจ้างจากไฟล์ 04_contract_data_to_fill.xlsx (data/ready3) — รันผ่าน:
    PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <ชื่อDB> --no-http < custom_addons/import_payslip_inputs/tools/create_contracts_shell.py

พฤติกรรม (idempotent รันซ้ำได้):
- พนักงานที่ยังไม่มีสัญญา  -> สร้างใหม่ state Running, Structure ตามกลุ่มสายงาน,
  วันเริ่มงานจากไฟล์, เงินเดือน = คอลัมน์ "เงินเดือน (กรอก)" ถ้ามี ไม่มีก็ 0 (โมเดล A ไม่ใช้คำนวณ)
- พนักงานที่มีสัญญาแล้ว   -> ถ้าไฟล์มีเงินเดือน (>0) และต่างจากในระบบ จะอัปเดต wage ให้
  (= ใช้สคริปต์เดียวกันนี้ตอน HR ส่งเงินเดือนจริงมาเติมทีหลัง)
- commit เฉพาะเมื่อไม่มี error"""
import openpyxl
import os
from odoo.modules.module import get_module_path

# หา path ของโมดูลอัตโนมัติ - ใช้ได้ทั้งเครื่อง dev และ production
SRC = os.path.join(get_module_path('import_payslip_inputs'), 'data', 'ready3',
                   '04_contract_data_to_fill.xlsx')

TYPE = {'บริหาร': env.ref('import_payslip_inputs.structure_type_executive'),
        'สำนักงาน': env.ref('import_payslip_inputs.structure_type_office'),
        'ผลิต-บริการ': env.ref('import_payslip_inputs.structure_type_factory'),
        'ผลิต-ชิ้นส่วน': env.ref('import_payslip_inputs.structure_type_factory'),
        'โรงงาน': env.ref('import_payslip_inputs.structure_type_factory')}

ws = openpyxl.load_workbook(SRC, data_only=True)['Data']
Emp = env['hr.employee']
Ct = env['hr.contract']
made = updated = skipped = errs = 0
for r in ws.iter_rows(min_row=2, values_only=True):
    code, name, job, branch, group, status, start, wage = (list(r) + [None] * 8)[:8]
    if code is None:
        continue
    code = str(code).strip()
    emp = Emp.search([('registration_number', '=', code), ('active', '=', True)], limit=1)
    if not emp:
        print('!! ไม่พบพนักงาน', code, name)
        errs += 1
        continue
    try:
        wage_val = float(str(wage).replace(',', '')) if wage not in (None, '') else 0.0
    except ValueError:
        print('!! เงินเดือนไม่ใช่ตัวเลข', code, wage)
        errs += 1
        continue
    ct = Ct.search([('employee_id', '=', emp.id)], limit=1)
    if ct:
        if wage_val > 0 and abs(ct.wage - wage_val) > 0.005:
            ct.wage = wage_val
            updated += 1
        else:
            skipped += 1
        continue
    stype = TYPE.get(str(group or '').strip())
    if not stype:
        print('!! ไม่รู้จักกลุ่มสายงาน', code, repr(group))
        errs += 1
        continue
    Ct.create({'name': f'สัญญาจ้าง - {emp.name}', 'employee_id': emp.id,
               'date_start': str(start)[:10] if start else '2026-01-01',
               'wage': wage_val, 'structure_type_id': stype.id, 'state': 'open'})
    made += 1

if errs:
    env.cr.rollback()
    print(f'พบปัญหา {errs} รายการ - ROLLED BACK (ไม่มีอะไรถูกบันทึก)')
else:
    env.cr.commit()
    print(f'สร้างใหม่ {made} | อัปเดตเงินเดือน {updated} | ไม่เปลี่ยน {skipped} | COMMITTED')
    print('สัญญา Running ทั้งหมด:', Ct.search_count([('state', '=', 'open')]))
