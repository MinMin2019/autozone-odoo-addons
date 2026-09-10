# -*- coding: utf-8 -*-
"""ตรวจสุขภาพระบบเงินเดือน — หาปัญหาที่ทำให้สลิป/บัญชีผิดโดยไม่มีใครรู้ (อ่านอย่างเดียว ไม่แก้อะไร)
รันทุกครั้งก่อนปิดงวด และหลังมีพนักงานเข้า/ออก:
    local: PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <DB> --no-http < custom_addons/import_payslip_inputs/tools/check_payroll_health_shell.py
    prod : ssh administrator@103.253.74.190 "cmd /c C:\\Users\\Administrator\\run_payroll_tool.cmd check_payroll_health_shell.py"
"""
from collections import Counter

Emp = env['hr.employee']
Ct = env['hr.contract']
problems = []


def report(title, recs, how, limit=10):
    """recs = list ของข้อความ"""
    if not recs:
        print(f'  [ok] {title}')
        return
    problems.append(title)
    print(f'  [!!] {title}: {len(recs)} รายการ')
    for r in recs[:limit]:
        print(f'        - {r}')
    if len(recs) > limit:
        print(f'        ... อีก {len(recs) - limit} รายการ')
    print(f'        วิธีแก้: {how}')


actives = Emp.search([('active', '=', True)])
seat_tag = env['hr.employee.category'].search([('name', '=', 'ตำแหน่งรักษาการ')], limit=1)
seats = actives.filtered(lambda e: seat_tag and seat_tag in e.category_ids)
staff = actives - seats
print(f'=== ตรวจสุขภาพระบบเงินเดือน === พนักงาน active {len(actives)} (พนักงานจริง {len(staff)} + เก้าอี้รักษาการ {len(seats)})')

print('--- ข้อมูลพนักงาน ---')
dup = [f'รหัส {code} ซ้ำ {n} คน' for code, n in
       Counter(staff.mapped('registration_number')).items() if code and n > 1]
report('รหัสพนักงานซ้ำ', dup, 'แก้รหัสให้ไม่ซ้ำ - ระบบเงินเดือนจับคู่ด้วยรหัสนี้')

report('พนักงานไม่มีรหัสพนักงาน',
       [f'{e.name} (id {e.id})' for e in staff.filtered(lambda e: not e.registration_number)],
       'ใส่รหัสในแท็บ HR Settings - ถ้าไม่มีรหัส ไฟล์เงินเดือนจะจับคู่ไม่เจอ สลิปเป็นศูนย์')

report('พนักงานไม่มีสาขา (Work Location)',
       [f'{e.registration_number} {e.name}' for e in staff.filtered(lambda e: not e.work_location_id)],
       'ใส่สาขา - ใช้กำหนดกอง Analytic ต้นทุนรายสาขา')

report('พนักงานไม่มี Tag กลุ่มสายงาน',
       [f'{e.registration_number} {e.name}' for e in staff.filtered(
           lambda e: not (e.category_ids - seat_tag))],
       'ใส่ Tag (ผลิต-บริการ/ผลิต-ชิ้นส่วน/สำนักงาน/บริหาร) - ใช้เลือกโครงสร้างเงินเดือน')

roots = actives.filtered(lambda e: not e.parent_id)
report('พนักงานไม่มีหัวหน้างาน (ควรเหลือแค่ยอดผัง 1 คน)',
       [f'{e.registration_number or "-"} {e.name}' for e in roots] if len(roots) > 1 else [],
       'ใส่ Manager ให้ครบ ไม่งั้นผังองค์กรขาดและ flow อนุมัติในอนาคตจะพัง')

print('--- สัญญาจ้าง ---')
no_ct = [f'{e.registration_number} {e.name}' for e in staff
         if not Ct.search_count([('employee_id', '=', e.id), ('state', '=', 'open')])]
report('พนักงานไม่มีสัญญาจ้าง Running', no_ct,
       'สร้างสัญญา (state Running) - ไม่มีสัญญา = Generate Payslips ข้ามคนนี้ ไม่มีสลิป ต้นทุนหายจากบัญชี')

open_cts = Ct.search([('state', '=', 'open')])
report('สัญญา Running ที่ไม่มีกอง Analytic',
       [f'{c.employee_id.registration_number} {c.employee_id.name}' for c in open_cts.filtered(
           lambda c: not c.analytic_account_id)],
       'รัน set_contract_analytic_shell.py - ไม่มี Analytic = ต้นทุนไม่เข้าสาขาในรายงาน')

our_structs = env['hr.payroll.structure'].search([('name', 'like', 'Legacy Import'), ('active', '=', True)])
report('สัญญา Running ที่ใช้โครงสร้างเงินเดือนผิด',
       [f'{c.employee_id.registration_number} {c.employee_id.name} -> {c.structure_type_id.default_struct_id.name or "(ไม่มี)"}'
        for c in open_cts.filtered(lambda c: c.structure_type_id.default_struct_id not in our_structs)],
       'แก้ Salary Structure Type ให้ตรงกลุ่มสายงาน (โรงงาน/สำนักงาน/ผู้บริหาร)')

report('เก้าอี้รักษาการที่มีสัญญาจ้าง (ต้องไม่มี)',
       [f'{e.name}' for e in seats if Ct.search_count([('employee_id', '=', e.id)])],
       'ลบสัญญาของกล่องเก้าอี้ - ไม่งั้นจะได้สลิปซ้ำและเงินเดือนเกิน')

archived_with_ct = Ct.search([('state', '=', 'open'), ('employee_id.active', '=', False)])
report('พนักงานที่ archive แล้วแต่สัญญายัง Running',
       [f'{c.employee_id.registration_number} {c.employee_id.name}' for c in archived_with_ct],
       'ปิดสัญญา (ใส่ End Date + สถานะ Expired) - ไม่งั้นอาจถูกดึงเข้างวดถัดไป')

print('--- การตั้งค่าบัญชี (wiring) ---')
bad_rules = []
for s in our_structs:
    for r in s.rule_ids:
        if r.code != 'GROSS' and not r.account_debit and not r.account_credit:
            bad_rules.append(f'{s.name} / {r.code}')
report('Salary Rule ที่ยังไม่ผูกบัญชี', bad_rules,
       'รัน wire_payroll_accounts_shell.py (กฎเหล็กข้อ 1 หลัง restore DB)')
j = env['account.journal'].search([('code', '=', 'PAYR')], limit=1)
report('สมุดรายวันเงินเดือน (PAYR)', [] if j else ['ยังไม่มี'],
       'รัน wire_payroll_accounts_shell.py')
report('โหมดใบสำคัญรวมทั้งงวด', [] if env.company.batch_payroll_move_lines else ['ยังปิดอยู่'],
       'รัน wire_payroll_accounts_shell.py - ถ้าปิดจะได้ใบสำคัญแยกรายคน (เงินเดือนรายคนโผล่ใน GL)')
report('โครงสร้างเงินเดือนที่ไม่มีสมุดรายวัน',
       [s.name for s in our_structs if not s.journal_id],
       'รัน wire_payroll_accounts_shell.py')

print('--- External ID (กันซ้ำตอน import รอบหน้า) ---')
no_xmlid = [f'{e.registration_number} {e.name}' for e in staff
            if not env['ir.model.data'].search_count(
                [('model', '=', 'hr.employee'), ('res_id', '=', e.id)])]
report('พนักงานที่ยังไม่มี External ID (สร้างมือ)', no_xmlid,
       'ไม่ต้องทำอะไร - import_all_shell.py จะผูกให้อัตโนมัติตอน import รอบหน้า (แค่ให้รู้ไว้)')

print()
if problems:
    print(f'*** พบปัญหา {len(problems)} หัวข้อ: {", ".join(problems)} ***')
else:
    print('*** ระบบสมบูรณ์ ไม่พบปัญหา พร้อมปิดงวด ***')
