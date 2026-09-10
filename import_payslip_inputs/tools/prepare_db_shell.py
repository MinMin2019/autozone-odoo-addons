# -*- coding: utf-8 -*-
"""เตรียม DB ใหม่ก่อน import พนักงาน — รันผ่าน odoo shell:
    PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <ชื่อDB> --no-http < custom_addons/import_payslip_inputs/tools/prepare_db_shell.py

สิ่งที่ทำ (idempotent รันซ้ำได้):
1. ลบ field/view ที่สร้างจาก Odoo Studio บน hr.employee (เช่น ช่องชื่อเล่น)
2. ลบ employee record ที่ถูกสร้างอัตโนมัติตอนสร้าง user (ไม่แตะ user!)
3. Archive employee ของ Administrator
เงื่อนไข: ต้องติดตั้งโมดูล import_payslip_inputs ก่อน (odoo-bin -i import_payslip_inputs)"""

fld = env['ir.model.fields'].search([('model', '=', 'hr.employee'), ('name', 'like', 'x_studio%')])
for f in fld:
    # พิมพ์ค่าที่มีอยู่ก่อนลบ กันข้อมูลหายเงียบ (บันทึกไว้ใน log)
    try:
        recs = env['hr.employee'].with_context(active_test=False).search([(f.name, '!=', False)])
        if recs:
            print(f"  ค่าที่มีใน {f.name} ({f.field_description}) ก่อนลบ:")
            for r in recs:
                print(f"    - {r.name} (id {r.id}): {r[f.name]!r}")
    except Exception as e:
        print("  อ่านค่าเดิมไม่ได้:", e)
    views = env['ir.ui.view'].search([('model', '=', 'hr.employee'), ('arch_db', 'like', f.name)])
    print("ลบ studio view:", views.mapped('name'))
    views.unlink()
    print("ลบ studio field:", f.name)
    f.unlink()

emps = env['hr.employee'].search([('active', '=', True)])
admin_emp = emps.filtered(lambda e: e.name == 'Administrator')
others = emps - admin_emp
if others:
    # กันลบพนักงานจริงโดยพลาด: DB ที่ import แล้วจะมี registration_number
    with_reg = others.filtered('registration_number')
    if with_reg:
        print(f"!! พบพนักงานที่มีรหัสพนักงาน {len(with_reg)} คน - ไม่ลบ (DB นี้อาจ import ไปแล้ว)")
    else:
        print("ลบ employee เก่าจากการสร้าง user:", len(others), "คน")
        others.unlink()
if admin_emp:
    admin_emp.write({'active': False})
    print("archive Administrator แล้ว")

env.cr.commit()
print("เหลือ employee active:", env['hr.employee'].search_count([('active', '=', True)]))
print("=== เตรียม DB เสร็จ (COMMITTED) ===")
