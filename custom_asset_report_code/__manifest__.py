# -*- coding: utf-8 -*-
{
    'name': "Custom Asset Code on Depreciation Schedule",
    'summary': "เพิ่มคอลัมน์ Asset Code ในรายงาน Depreciation Schedule",
    'description': """
เพิ่มคอลัมน์ Asset Code (x_studio_asset_code) เป็นคอลัมน์แรกของรายงาน
Depreciation Schedule (Accounting > Reporting > Depreciation Schedule)
รวมถึงตอน export PDF / XLSX
    """,
    'author': 'Autozone',
    'website': "https://www.autozonegroup.com",
    'category': 'Autozone/Accounting',
    'version': '1.0',
    'depends': ['account_asset'],
    'data': [
        'data/assets_report.xml',
    ],
    'license': 'LGPL-3',
}
