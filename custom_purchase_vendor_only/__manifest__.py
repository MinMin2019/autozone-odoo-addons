# -*- coding: utf-8 -*-
{
    'name': 'Purchase: Vendor-only Partner List',
    'summary': 'ช่อง Vendor ในใบสั่งซื้อแสดงเฉพาะผู้ขาย + checkbox "Is a Vendor" บนฟอร์ม Contact',
    'version': '18.0.1.1.0',
    'category': 'Autozone/Purchase',
    'author': 'Autozone',
    'license': 'LGPL-3',
    'depends': ['purchase'],
    'data': [
        'views/purchase_order_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
}
