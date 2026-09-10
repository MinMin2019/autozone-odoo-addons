# -*- coding: utf-8 -*-
"""ผูกกอง Analytic รายสาขาลงสัญญาจ้างทุกใบ (ต้นทุนเงินเดือนรายสาขา) — รันผ่าน:
    PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <ชื่อDB> --no-http < custom_addons/import_payslip_inputs/tools/set_contract_analytic_shell.py

หลักการ: จับคู่ รหัสสาขาของพนักงาน (Work Location) = ช่อง Code ของกอง Analytic
กรณีพิเศษ: AZG (สำนักงานใหญ่) -> กอง code "H.O." (ยืนยันโดยผู้ใช้ 27 ส.ค. 2026)
Idempotent: รันซ้ำได้ อัปเดตเฉพาะสัญญาที่ค่ายังไม่ตรง | รันซ้ำเมื่อ: มีพนักงาน/สาขาใหม่ หรือหลัง restore DB
ผลที่ได้: ใบสำคัญเงินเดือนแตกยอดตามมิติสาขาอัตโนมัติทุกงวด (มิติเดียวกับเงินสดย่อย)"""

SPECIAL = {'AZG': 'H.O.'}

Analytic = env['account.analytic.account']
by_code = {}
for a in Analytic.search([('code', '!=', False)]):
    by_code[a.code.strip().upper()] = a

contracts = env['hr.contract'].search([('employee_id.active', '=', True),
                                       ('employee_id.registration_number', '!=', False)])
set_n = skip = 0
missing = {}
for ct in contracts:
    branch = (ct.employee_id.work_location_id.name or '').strip().upper()
    if not branch:
        missing.setdefault('(ไม่มีสาขา)', []).append(ct.employee_id.registration_number)
        continue
    target = by_code.get(SPECIAL.get(branch, branch))
    if not target:
        missing.setdefault(branch, []).append(ct.employee_id.registration_number)
        continue
    if ct.analytic_account_id == target:
        skip += 1
    else:
        ct.analytic_account_id = target
        set_n += 1

env.cr.commit()
print(f'ตั้ง Analytic ใหม่ {set_n} สัญญา | ตรงอยู่แล้ว {skip} | COMMITTED')
if missing:
    for b, codes in missing.items():
        print(f'!! ไม่พบกองของสาขา {b}: {len(codes)} คน เช่น {codes[:5]}')
else:
    print('จับคู่ครบทุกสัญญา ไม่มีตกหล่น')

# สรุปต่อกอง
from collections import Counter
c = Counter(ct.analytic_account_id.code or '-' for ct in contracts if ct.analytic_account_id)
print('สัญญาต่อกอง:', dict(sorted(c.items())))
