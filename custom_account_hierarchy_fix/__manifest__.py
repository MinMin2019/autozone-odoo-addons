# -*- coding: utf-8 -*-
{
    "name": "Autozone Account Hierarchy Fix",
    "summary": "แก้บั๊ก sh_account_parent: Auto Unfold, ปุ่ม Print, กัน Parent วนลูป "
    "+ สิทธิ์ Account Hierarchy Viewer",
    "description": """
แพตช์โมดูล sh_account_parent (Softhealer) โดยไม่แตะไฟล์ third_party:

- Auto Unfold ทำงานจริง (เดิม update_context ลืม return ทำให้ context ว่าง
  และ wizard ที่ใช้คำนวณอาจเป็นตัวเก่า)
- ปุ่ม Print ในหน้ารายงานใช้งานได้ (เดิมเรียกเมธอดที่ไม่มีอยู่)
- ห้ามตั้ง Parent Account ชี้ตัวเอง/วนลูป และ Parent ต้องเป็นบัญชี Type View
  (กันเคสบัญชีหายจากรายงาน + server ค้างจาก recursion)
- กดกางบัญชี View ที่ยังไม่มีลูก จะแจ้งเตือนแทนที่จะเงียบ
- กลุ่มสิทธิ์ "Account Hierarchy Viewer" คุมเมนู Chart of Accounts Hierarchy
  (ผู้ใช้กลุ่มบัญชีเดิมได้รับสิทธิ์อัตโนมัติ ไม่มีใครเสียเมนูที่เคยเห็น)
- ตัวช่วย "Account Groups จากผังแม่": แปลงผังแม่ (บัญชี Type View) เป็น
  account.group ให้รายงานมาตรฐาน (P&L / งบดุล / งบทดลอง) แสดงเป็นชั้น
  พร้อมยอดรวมย่อยเมื่อเปิด Options -> Hierarchy and Subtotals
  มีปุ่มตรวจก่อน (dry-run) รายงานเคสที่แปลงไม่ได้ให้ตัดสินใจ
""",
    "author": "Autozone",
    "category": "Autozone/Accounting",
    "version": "18.0.1.2.0",
    "license": "LGPL-3",
    "depends": ["sh_account_parent", "account_reports"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/account_group_sync_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "custom_account_hierarchy_fix/static/src/js/hierarchy_fix.js",
        ],
    },
    "installable": True,
    "application": False,
}
