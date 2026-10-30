# -*- coding: utf-8 -*-
{
    'name': 'iGarage Mobile Usage (การใช้แอปลงเวลาช่าง)',
    'version': '18.0.1.0.3',
    'category': 'Autozone/Tools',
    'summary': 'ติดตามการใช้แอปมือถือลงเวลาช่างของระบบ iGarage รายสาขา รายจ๊อบ รายช่าง',
    'description': """
ติดตามการใช้แอปมือถือลงเวลาช่าง (iGarage)
==========================================
ดึงข้อมูลการลงเวลาช่างจากฐาน MySQL ของระบบ iGarage (อ่านอย่างเดียว) มาเก็บใน Odoo
แล้วแยกว่าชิ้นงานไหนบันทึกผ่านแอปมือถือ ชิ้นไหนบันทึกผ่าน PC

- ใช้แอป: ดูจาก log เว็บเซิร์ฟเวอร์ของ iGarage (โหลดผ่าน FTPS) ว่าแอปยิงคำสั่งลงเวลา
  ตอนวินาทีไหน แล้วจับคู่กับแถวในฐาน — log ได้วันละครั้งตอนเที่ยงคืน ตัวเลขนี้จึงช้า 1 วัน
- ลงเวลาตรง: กดเริ่มกับกดจบห่างกันเกิน 60 วินาที (นับเป็นจ๊อบ = เริ่มชิ้นแรกถึงจบชิ้นสุดท้าย)
- ไม่รวมสาขาที่ไม่ใช่งานอู่ (ค่าเริ่มต้น AKT, AMU)

ตั้งค่า (Settings > Technical > System Parameters):
  igarage.db_host / igarage.db_port / igarage.db_name / igarage.db_user / igarage.db_password
  igarage.ftp_host / igarage.ftp_user / igarage.ftp_password
  igarage.since_date (ค่าเริ่มต้น 2026-10-01), igarage.exclude_branch_ids (ค่าเริ่มต้น 32,33)

ไลบรารี PyMySQL (MIT) ฝังไว้ใน lib/ ไม่ต้องติดตั้งเพิ่มบนเครื่อง server
    """,
    'author': 'Autozone',
    'depends': ['base', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/igarage_usage_views.xml',
        'views/igarage_sync_views.xml',
        'views/igarage_usage_menus.xml',
        'data/ir_cron.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
