# -*- coding: utf-8 -*-
{
    'name': 'Autozone Employee Loan',
    'version': '18.0.1.2.0',
    'category': 'Autozone/HR',
    'summary': 'ทะเบียนเงินกู้สวัสดิการพนักงาน + ส่งยอดหักงวดเข้า Payslip Batch',
    'description': """
Autozone Employee Loan (เงินกู้สวัสดิการพนักงาน)
================================================
- ทะเบียนเงินกู้รายคน: เงินต้น งวดผ่อน ตารางหักรายเดือน ยอดคงเหลือ
- ปุ่ม "หักเงินกู้พนักงาน" บน Payslip Batch: ดึงงวดที่ถึงกำหนดของพนักงานใน Batch
  สร้างเป็น Other Input รหัส LOAN (โครงสร้าง Legacy Import มี Salary Rule รองรับอยู่แล้ว)
- งวดถูกตัดเป็น "หักแล้ว" อัตโนมัติเมื่อสลิปถูก Validate (คำนวณจากสถานะสลิป ไม่ override core)
- เลขที่รันอัตโนมัติ LC<ปี พ.ศ.>/NNN (รีเซ็ตทุกปี) แก้มือได้จนกว่าจะปิดยอด ห้ามซ้ำ
- รองรับชำระเอง/โปะปิดยอด (ติ๊กชำระเองที่งวด พร้อมหมายเหตุ)
- โมดูลเป็นแบบเพิ่มของใหม่ล้วน ไม่แก้พฤติกรรมเดิมของ payroll/บัญชี
  ถ้าไม่กดปุ่มก็ไม่มีผลใด ๆ กับ flow ปัจจุบัน (ใช้ Excel ต่อได้ตามเดิม)

หมายเหตุฝั่งบัญชี: JE จ่ายเงินกู้ (Dr เงินให้กู้ยืมพนักงาน / Cr ธนาคาร) ยังลงมือใน
Accounting ตามปกติ แล้วผูกเลข JE ไว้ที่ทะเบียนเพื่ออ้างอิง/กระทบยอด
    """,
    'author': 'Autozone',
    'depends': ['hr_payroll', 'import_payslip_inputs', 'accountant'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/hr_payslip_input_type_data.xml',
        'views/hr_employee_loan_views.xml',
        'wizard/loan_push_wizard_views.xml',
        'views/hr_payslip_run_views.xml',
        'views/hr_employee_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
