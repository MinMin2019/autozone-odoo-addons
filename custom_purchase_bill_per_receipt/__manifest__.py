# -*- coding: utf-8 -*-
{
    "name": "Purchase: Bill per Receipt",
    "summary": "ออกบิลผู้ขายแยกตามใบรับสินค้า — รับ 2 ครั้งได้บิล 2 ใบ จำนวนตรงกับใบรับใบนั้น + เมนูบัญชี \"ใบรับสินค้าค้างตั้งหนี้\" ให้ทีมบัญชีออกบิลได้เองโดยไม่ต้องเข้าเมนูจัดซื้อ",
    "version": "18.0.1.1.0",
    "category": "Autozone/Purchase",
    "author": "Autozone",
    "license": "LGPL-3",
    "depends": ["purchase_stock", "account"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/purchase_bill_receipt_wizard_views.xml",
        "views/stock_picking_views.xml",
        "views/purchase_order_views.xml",
        "views/account_move_views.xml",
        "views/account_menu_views.xml",
    ],
    "installable": True,
    "application": False,
}
