# -*- coding: utf-8 -*-
{
    "name": "Purchase: Smarter Bill Auto-Complete",
    "summary": "ช่อง Auto-Complete บนบิลผู้ขาย: กรองบรรทัดที่ไม่มีอะไรให้ตั้งหนี้ออก (เหมือนปุ่ม Create Bill) + เตือนเมื่อ PO ยังไม่มีของรับ + เปิดให้ทีมบัญชีเห็นช่องนี้โดยไม่ต้องมีสิทธิ์จัดซื้อ",
    "version": "18.0.1.0.0",
    "category": "Autozone/Purchase",
    "author": "Autozone",
    "license": "LGPL-3",
    "depends": ["purchase"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}
