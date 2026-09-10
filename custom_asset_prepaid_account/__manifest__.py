# -*- coding: utf-8 -*-
{
    'name': 'Autozone Asset Prepaid Account',
    'summary': 'ให้เลือกบัญชีประเภท Prepayments (ค่าใช้จ่ายจ่ายล่วงหน้า) ในฟอร์มสินทรัพย์ได้',
    'description': """
ฟอร์ม Asset ของ Odoo ล็อก domain ของช่อง Fixed Asset Account / Depreciation Account
ไว้ที่ account_type in (asset_fixed, asset_non_current, asset_current) เท่านั้น
ทำให้บัญชีในผังบัญชีที่ตั้งประเภทเป็น "Prepayments" เช่น

  152101 ค่าเงินเดือนจ่ายล่วงหน้า
  152102 ค่าเบี้ยประกันภัยจ่ายล่วงหน้า
  152103 ค่าใช้จ่ายจ่ายล่วงหน้าอื่นๆ

ไม่โผล่ในดรอปดาวน์ (ค้นหาก็ไม่เจอ) ทั้งที่บัญชีไม่ได้ถูกปิดใช้งาน

โมดูลนี้เพิ่ม 'asset_prepayments' เข้าไปใน domain ของทั้ง 2 ช่อง ทั้งในฟอร์ม
สินทรัพย์ปกติและฟอร์ม Asset Model — ไม่แตะผังบัญชี ไม่กระทบงบการเงิน
(บัญชียังอยู่ใต้หัวข้อ Prepayments ในงบดุลเหมือนเดิม)

ช่อง Expense Account ยังคงเดิม (expense / expense_depreciation) โดยตั้งใจ
เพราะปลายทางของการทยอยตัดต้องลงงบกำไรขาดทุน
""",
    'version': '18.0.1.0.0',
    'category': 'Autozone/Accounting',
    'author': 'Autozone',
    'license': 'LGPL-3',
    'depends': [
        'account_asset',
    ],
    'data': [
        'views/account_asset_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
