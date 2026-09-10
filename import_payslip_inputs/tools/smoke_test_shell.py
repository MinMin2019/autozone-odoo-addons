# -*- coding: utf-8 -*-
"""สโมคเทสต์ระบบเงินเดือนทั้งสาย (ปลอดภัย 100% - rollback เสมอ ไม่มีข้อมูลค้าง) — รันผ่าน:
    PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <ชื่อDB> --no-http < custom_addons/import_payslip_inputs/tools/smoke_test_shell.py

ทดสอบ: สร้าง Batch + สลิป 2 คน (ผู้บริหาร + โรงงาน) -> ใส่ยอด -> คำนวณ -> ยืนยัน
แล้วตรวจใบสำคัญ: ต้องได้ 1 ใบ, สมุดรายวันเงินเดือน, แยกบัญชีตามกลุ่ม, ดุลเป๊ะ
ใช้ตรวจหลังติดตั้ง/หลัง restore DB/ก่อนเปิดงวดจริง — ถ้าผลไม่ตรง "ผลที่คาดหวัง" ด้านล่าง
มักลืมรัน wire_payroll_accounts_shell.py (ดู IMPORT_GUIDE ข้อ 4.3)

ผลที่คาดหวัง: ใบสำคัญ 1 ใบ | สมุด 'สมุดรายวันเงินเดือน' | ดุล Dr = Cr = 115,275
บรรทัดหลัก: Dr 621000 100,000 / 511000 12,000 / 511001 1,500 / 511007 500 /
            621012 750 / 511012 525 | Cr 232001 107,625 / 232010 2,550 (2 บรรทัด) /
            231001 5,000 / 710002 100"""
import traceback

try:
    Emp = env['hr.employee']
    exe_emp = Emp.search([('registration_number', '!=', False), ('active', '=', True)]).filtered(
        lambda e: e.contract_id and 'ผู้บริหาร' in e.contract_id.structure_type_id.default_struct_id.name)[:1]
    fac_emp = Emp.search([('registration_number', '!=', False), ('active', '=', True)]).filtered(
        lambda e: e.contract_id and 'โรงงาน' in e.contract_id.structure_type_id.default_struct_id.name)[:1]
    if not exe_emp or not fac_emp:
        raise Exception('ไม่พบพนักงานที่มีสัญญา Running ครบสองกลุ่ม - สร้างสัญญาก่อน (create_contracts_shell.py)')
    print('ทดสอบด้วย:', exe_emp.name, '(ผู้บริหาร) +', fac_emp.name, '(โรงงาน)')

    batch = env['hr.payslip.run'].create({'name': 'SMOKE TEST (จะถูก rollback)',
                                          'date_start': '2026-08-01', 'date_end': '2026-08-31'})
    slips = env['hr.payslip']
    for emp in (exe_emp, fac_emp):
        struct = emp.contract_id.structure_type_id.default_struct_id
        slips |= env['hr.payslip'].create({
            'name': f'สลิป {emp.name}', 'employee_id': emp.id, 'contract_id': emp.contract_id.id,
            'struct_id': struct.id, 'payslip_run_id': batch.id,
            'date_from': '2026-08-01', 'date_to': '2026-08-31'})

    def add(slip, code, amt):
        t = env['hr.payslip.input.type'].search([('code', '=', code)], limit=1)
        if not t:
            raise Exception('ไม่พบ input type ' + code)
        env['hr.payslip.input'].create({'payslip_id': slip.id, 'input_type_id': t.id, 'amount': amt})

    s_exe, s_fac = slips[0], slips[1]
    add(s_exe, 'BASIC', 100000); add(s_exe, 'SSO', 750); add(s_exe, 'TAX', 5000); add(s_exe, 'SSO_EMPLOYER', 750)
    add(s_fac, 'BASIC', 12000); add(s_fac, 'OT', 1500); add(s_fac, 'DILIGENCE', 500)
    add(s_fac, 'SSO', 525); add(s_fac, 'SSO_EMPLOYER', 525); add(s_fac, 'LOAN_INT', 100)
    slips.compute_sheet()
    slips.action_payslip_done()
    moves = slips.mapped('move_id')
    print(f"\nใบสำคัญ: {len(moves)} ใบ (คาด 1) | สมุด: {moves.journal_id.mapped('name')} | สถานะ: {set(moves.mapped('state'))}")
    for l in moves.line_ids.sorted(lambda x: (-x.debit, x.account_id.code)):
        print(f"  {l.account_id.code} {l.account_id.name[:34]:34} Dr {l.debit:>10,.2f}  Cr {l.credit:>10,.2f}")
    dr = sum(moves.line_ids.mapped('debit'))
    cr = sum(moves.line_ids.mapped('credit'))
    print(f"ดุล: Dr {dr:,.2f} = Cr {cr:,.2f}", '<-- คาด 115,275.00 ทั้งสองฝั่ง')
    verdict = (len(moves) == 1 and abs(dr - 115275) < 0.01 and abs(dr - cr) < 0.01)
    print('\n***** ผลทดสอบ:', 'ผ่าน *****' if verdict else 'ไม่ผ่าน - ตรวจ wiring (IMPORT_GUIDE 4.3) *****')
except Exception:
    traceback.print_exc()
env.cr.rollback()
print('ROLLED BACK - ไม่มีข้อมูลทดสอบค้างใน DB')
