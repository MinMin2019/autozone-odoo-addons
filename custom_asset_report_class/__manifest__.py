# -*- coding: utf-8 -*-
{
    'name': "Custom Group by Analytic on Depreciation Schedule",
    'summary': "เพิ่มตัวเลือกจัดกลุ่มตาม Analytic + คอลัมน์ Analytic ในรายงาน Depreciation Schedule",
    'description': """
เพิ่มตัวเลือกที่สามในปุ่มจัดกลุ่มของรายงาน Depreciation Schedule
(Accounting > Reporting > Depreciation Schedule):

- จัดกลุ่มตามบัญชี (ของเดิม)
- จัดกลุ่มตามกลุ่มสินทรัพย์ (ของเดิม)
- **จัดกลุ่มตาม Analytic** — อิง Analytic Distribution ของสินทรัพย์ (ช่องเดียวกับที่
  ค่าเสื่อมลงบัญชีจริง) พร้อมยอดรวมต่อ Analytic; สินทรัพย์ที่แบ่งหลายสาขาจะแตกเป็น
  หลายบรรทัด ยอดเงินคูณตาม % (เช่น "อาคาร (52%)") ยอดรวมทั้งรายงานเท่าเดิม
  สินทรัพย์ที่ไม่ได้ระบุ Analytic จะรวมอยู่ในกลุ่ม "(No Analytic)" ท้ายรายงาน

และเพิ่มคอลัมน์ **Analytic** แสดง Analytic Distribution ของสินทรัพย์แต่ละตัว
(ตัวเดียว 100% แสดงแค่ชื่อ, หลายตัวแสดงเป็น "75% ก + 25% ข")

v1.1 (1 ต.ค. 2026): เลิกใช้ฟิลด์ Class (x_class_id) เพราะซ้ำกับ Analytic Distribution
และคีย์ไม่ตรงกันบางรายการ — ซ่อนช่อง Class บนฟอร์ม (ข้อมูลเดิมยังอยู่)

รวมถึงตอน export PDF / XLSX
    """,
    'author': 'Autozone',
    'website': "https://www.autozonegroup.com",
    'category': 'Autozone/Accounting',
    'version': '1.1',
    'depends': ['account_asset', 'asset_module'],
    'data': [
        'data/assets_report.xml',
        'views/account_asset_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_asset_report_class/static/src/components/**/*',
        ],
    },
    'license': 'LGPL-3',
}
