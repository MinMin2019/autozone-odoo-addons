{
    "name": "Slow / Dead Stock Report (สินค้าเคลื่อนไหวช้า)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "สินค้าเคลื่อนไหวช้า/ไม่เคลื่อนไหว ต่อสินค้าต่อสาขา: อัตราการใช้ย้อนหลัง 30/90/180/365 วัน, เดือนที่พอใช้, จัดชั้น Dead/Slow/Normal, สาขาที่ยังใช้อยู่ (โยกของแทนซื้อใหม่)",
    "description": """
รายงานสินค้าเคลื่อนไหวช้า / ไม่เคลื่อนไหว (Slow-moving / Dead stock) ตามมาตรฐาน ERP

* ยอดคงเหลือ ณ วันที่ ต่อสินค้าต่อสาขา (หรือรวมทุกสาขา) + มูลค่า
* การใช้ย้อนหลัง (ส่งขาย / เบิกใช้ / โอนออก) 30, 90, 180, 365 วัน + วันที่ใช้ล่าสุด + จำนวนวันที่ไม่ได้ใช้
* ค่าเฉลี่ยการใช้ต่อเดือน + "พอใช้อีกกี่เดือน" (คงเหลือ ÷ ค่าเฉลี่ย)
* จัดชั้นอัตโนมัติ (ตั้งเกณฑ์ได้): Dead = ไม่ได้ใช้เกิน N วัน, Slow = พอใช้เกิน X เดือน, Normal
* สาขาอื่นที่ยังใช้สินค้าตัวนั้นอยู่ใน 90 วัน (สูงสุด 3 สาขา) ให้โยกของแทนซื้อใหม่
* list / pivot / graph + PDF + Excel
    """,
    "depends": ["stock", "stock_account", "autozone_report_fonts"],
    "data": [
        "security/ir.model.access.csv",
        "report/stock_slow_moving_report.xml",
        "wizard/stock_slow_moving_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
