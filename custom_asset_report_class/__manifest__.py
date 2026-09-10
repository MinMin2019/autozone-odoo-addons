# -*- coding: utf-8 -*-
{
    'name': "Custom Group by Class on Depreciation Schedule",
    'summary': "เพิ่มตัวเลือกจัดกลุ่มตามคลาส + คอลัมน์ Analytic ในรายงาน Depreciation Schedule",
    'description': """
เพิ่มตัวเลือกที่สามในปุ่มจัดกลุ่มของรายงาน Depreciation Schedule
(Accounting > Reporting > Depreciation Schedule):

- จัดกลุ่มตามบัญชี (ของเดิม)
- จัดกลุ่มตามกลุ่มสินทรัพย์ (ของเดิม)
- **จัดกลุ่มตามคลาส** — อิงฟิลด์ Class (x_class_id จากโมดูล asset_module
  ชี้ไปที่ Analytic Account เช่น ATZ / ATP) พร้อมยอดรวมต่อคลาส
  สินทรัพย์ที่ไม่ได้ระบุคลาสจะรวมอยู่ในกลุ่ม "(No Class)" ท้ายรายงาน

และเพิ่มคอลัมน์ **Analytic** แสดง Analytic Distribution ของสินทรัพย์แต่ละตัว
(ตัวเดียว 100% แสดงแค่ชื่อ, หลายตัวแสดงเป็น "75% ก + 25% ข")

รวมถึงตอน export PDF / XLSX
    """,
    'author': 'Autozone',
    'website': "https://www.autozonegroup.com",
    'category': 'Autozone/Accounting',
    'version': '1.0',
    'depends': ['account_asset', 'asset_module'],
    'data': [
        'data/assets_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_asset_report_class/static/src/components/**/*',
        ],
    },
    'license': 'LGPL-3',
}
