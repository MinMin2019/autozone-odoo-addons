# -*- coding: utf-8 -*-
"""Import พนักงานทั้งชุดจาก data/ready2 — รันผ่าน odoo shell:
    PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <ชื่อDB> --no-http < custom_addons/import_payslip_inputs/tools/import_all_shell.py

ลำดับ: แผนก -> สาขา -> พนักงาน -> หัวหน้างาน -> ผูก user
ปลอดภัย: commit เฉพาะเมื่อ error = 0 ทุกไฟล์ ไม่งั้น rollback ทั้งหมด
รันซ้ำได้: External ID เดิม = อัปเดตคนเดิม ไม่สร้างซ้ำ"""
import openpyxl
import os
from odoo.modules.module import get_module_path

# หา path ของโมดูลอัตโนมัติ - ใช้ได้ทั้งเครื่อง dev และ production
BASE = os.path.join(get_module_path('import_payslip_inputs'), 'data', 'ready3')
PLAN = [('hr.department', '00a_departments.xlsx'),
        ('hr.work.location', '00b_work_locations.xlsx'),
        ('hr.employee', '01_employees_READY.xlsx'),
        ('hr.employee', '02_managers.xlsx'),
        ('hr.employee', '03_link_users.xlsx')]


def read(fname):
    ws = openpyxl.load_workbook(os.path.join(BASE, fname))['Data']
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h) for h in rows[0]]
    data = [[str(v) if v is not None else '' for v in r] for r in rows[1:]]
    return headers, data


env2 = env(user=2, context=dict(env.context, allowed_company_ids=[1], import_file=True,
           name_create_enabled_fields={'job_id': True, 'category_ids': True}))

# --- ซ่อมอัตโนมัติ: ผูก External ID ให้พนักงานที่ถูกสร้างมือในหน้าเว็บ ---
# ถ้าไม่ทำ: รหัสพนักงานซ้ำ -> import ล้มทั้งชุด (error หลอกว่า "resource.resource does not exist")
_h, _rows = read('01_employees_READY.xlsx')
_i_id, _i_reg = _h.index('id'), _h.index('registration_number')
_healed = []
for _r in _rows:
    _xmlid, _reg = _r[_i_id], _r[_i_reg]
    if not _xmlid or not _reg:
        continue
    if env.ref('__import__.' + _xmlid, raise_if_not_found=False):
        continue
    _emp = env['hr.employee'].with_context(active_test=False).search(
        [('registration_number', '=', _reg)], limit=1)
    if _emp:
        env['ir.model.data'].create({'module': '__import__', 'name': _xmlid,
                                     'model': 'hr.employee', 'res_id': _emp.id})
        _healed.append(f'{_reg} {_emp.name}')
if _healed:
    print(f'ผูก External ID ให้พนักงานที่สร้างมือ {len(_healed)} คน: {_healed[:8]}'
          + (' ...' if len(_healed) > 8 else ''))

ok = True
for model, fname in PLAN:
    headers, data = read(fname)
    res = env2[model].load(headers, data)
    errs = [m for m in res.get('messages', []) if m.get('type') == 'error']
    print(f"{fname}: created/updated {len(res.get('ids') or [])} | errors {len(errs)}")
    for m in errs[:5]:
        print("   ERR:", str(m.get('message'))[:160])
    if errs or not res.get('ids'):
        ok = False
        break

if ok:
    env.cr.commit()
    print("\n=== COMMITTED ===")
    print("พนักงาน active:", env['hr.employee'].search_count([('active', '=', True)]))
    roots = env['hr.employee'].search([('active', '=', True), ('parent_id', '=', False)])
    print("ยอดผัง:", [(r.name, r.registration_number) for r in roots])
    print("ผูก user:", env['hr.employee'].search_count([('active', '=', True), ('user_id', '!=', False)]))
else:
    env.cr.rollback()
    print("\n=== ROLLED BACK - ไม่มีอะไรถูกบันทึก แก้ไฟล์แล้วรันใหม่ ===")
