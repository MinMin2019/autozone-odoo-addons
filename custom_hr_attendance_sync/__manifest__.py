# -*- coding: utf-8 -*-
{
    'name': 'Autozone Attendance Sync (BpControl)',
    'version': '18.0.1.1.0',
    'category': 'Autozone/HR',
    'summary': 'ดึงเวลาตอกบัตรจากเครื่องสแกนนิ้ว (ฐาน BpControl บน SQL Server) เข้า Attendances',
    'description': """
เฟส 2 ระบบเงินเดือน — ตัวดึงเวลาตอกบัตร
========================================
ดึงข้อมูลสแกนนิ้วมือ "ของดิบ" จากตาราง BpControl.dbo.ScanData (โปรแกรม Windows
ดึงจากเครื่องสแกนมาลง SQL Server อยู่แล้ว) เข้าเป็นบันทึกเวลา hr.attendance ของ Odoo

- 1 วันของพนักงาน 1 คน = ได้สูงสุด 3 ช่วง (เช้า m1-m2 / บ่าย a1-a2 / เย็น-โอที e1-e2)
- จับคู่พนักงานด้วย atzScanId = Registration Number (รหัสพนักงาน 5 หลัก)
- แปลงเวลา Asia/Bangkok -> UTC ให้อัตโนมัติ
- รันซ้ำได้ (idempotent): ถ้าฝั่ง BpControl แก้เวลาย้อนหลัง การดึงรอบใหม่จะอัปเดต/ลบตาม
- cron รายวัน ดึงย้อนหลัง N วัน (ค่าเริ่มต้น 7) เพื่อรับการแก้ไขย้อนหลังของหัวหน้าสาขา
- ทุกรอบบันทึกผลไว้ในเมนู "ประวัติการดึงเวลา" (สร้าง/แก้/ลบ/ข้าม/ไม่พบพนักงาน)

ระยะนี้ยังไม่แตะการคำนวณเงินเดือน — เก็บข้อมูลขนานไปกับ Business Plus เพื่อสะสมไว้
เทียบผลก่อนตัดระบบจริงในปี พ.ศ. 2570

ค่าเชื่อมต่อ (Settings > Technical > System Parameters):
  bpcontrol.server / bpcontrol.database / bpcontrol.user / bpcontrol.password
  (ถ้าไม่ตั้ง จะใช้ค่า bplus.* ของโมดูล import_payslip_inputs ยกเว้น database = BpControl)
  bpcontrol.sync_days = จำนวนวันย้อนหลังที่ cron ดึงทุกวัน (ค่าเริ่มต้น 7)
    """,
    'author': 'Autozone',
    'depends': ['hr_attendance', 'import_payslip_inputs'],
    'external_dependencies': {'python': ['pyodbc']},
    'data': [
        'security/ir.model.access.csv',
        'views/az_attendance_sync_views.xml',
        'wizard/az_attendance_sync_wizard_views.xml',
        'views/hr_attendance_views.xml',
        'data/ir_cron.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
