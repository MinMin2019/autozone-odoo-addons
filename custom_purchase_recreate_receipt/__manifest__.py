# -*- coding: utf-8 -*-
{
    "name": "Purchase: Recreate Cancelled Receipt",
    "summary": "ปุ่ม \"สร้างใบรับใหม่\" บนใบสั่งซื้อ เมื่อใบรับสินค้าถูกยกเลิกไปหมดแล้วแต่ยังมีของค้างรับ",
    "version": "18.0.1.0.0",
    "category": "Autozone/Purchase",
    "author": "Autozone",
    "license": "LGPL-3",
    "depends": ["purchase_stock"],
    "data": [
        "views/purchase_order_views.xml",
    ],
    "installable": True,
    "application": False,
}
