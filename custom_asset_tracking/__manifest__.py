# -*- coding: utf-8 -*-
{
    'name': 'Autozone Asset Tracking',
    'summary': 'แอป Assets: ผู้ถือครอง, ตรวจนับ, ใบส่งมอบ/ส่งคืนทรัพย์สิน',
    'description': """
เฟส 1a ของระบบติดตามทรัพย์สิน: เพิ่มช่อง Custodian (hr.employee) บนสินทรัพย์
แทนช่อง Repository เดิมที่พิมพ์ชื่อคนเป็นข้อความ (ช่องเดิมถูกซ่อน ข้อมูลยังอยู่)

ตอนติดตั้งจะย้ายชื่อเดิมที่ตรงกับพนักงานให้อัตโนมัติ (ตัดคำนำหน้า/ช่องว่างก่อนเทียบ)
ชื่อที่จับคู่ไม่ได้ปล่อยว่าง ให้ฝ่ายบัญชีเลือกเอง
""",
    'version': '18.0.1.8.0',
    'category': 'Autozone/Assets',
    'author': 'Autozone',
    'website': 'https://www.autozonegroup.com',
    'license': 'LGPL-3',
    'depends': [
        'account_asset',
        'hr',
        'asset_module',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/account_asset_views.xml',
        'views/asset_image_views.xml',
        'views/menus.xml',
        'views/asset_handover_views.xml',
        'report/asset_check_report.xml',
        'report/asset_handover_report.xml',
        'wizard/asset_check_report_wizard_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
}
