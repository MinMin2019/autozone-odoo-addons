# -*- coding: utf-8 -*-
{
    'name': 'Autozone Studio Fields (Backup)',
    'summary': 'สำรองฟิลด์ที่สร้างผ่าน Odoo Studio ให้อยู่ในรูปโค้ด สำหรับกรณีอัพเกรด/ย้ายฐานข้อมูล',
    'description': """
เก็บฟิลด์ที่ถูกสร้างแบบ manual ผ่าน Odoo Studio บน DB Autozone-PD ให้อยู่ในรูปโมดูล
เพื่อไม่ให้ฟิลด์/ข้อมูลหายเวลาอัพเกรดเวอร์ชันหรือสร้างฐานข้อมูลใหม่

**ยังไม่ต้องติดตั้งบน DB ปัจจุบัน** — ฟิลด์มีอยู่แล้วในฐานข้อมูล (state=manual)
ติดตั้งเมื่อไหร่ Odoo จะ "รับช่วง" ฟิลด์เดิมให้กลายเป็นฟิลด์ของโมดูล (ข้อมูลไม่หาย
เพราะชื่อคอลัมน์ตรงกันทุกตัว) — อ่านเงื่อนไขและรายการฟิลด์ทั้งหมดใน README.md ของโมดูลนี้
""",
    'version': '18.0.1.0.0',
    'category': 'Autozone/Tools',
    'author': 'Autozone',
    'license': 'LGPL-3',
    'depends': [
        'account_asset',   # ฟิลด์บน account.asset
        'asset_module',    # view อ้าง x_location_id / x_class_id ของโมดูลนี้
        'sale',            # related journal_id บน sale.order
    ],
    'data': [
        'views/account_asset_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
