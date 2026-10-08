{
    "name": "Autozone Stock Count Sheet (ใบตรวจนับสต็อก)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "ใบตรวจนับสต็อกประจำสาขา: ดึงรายการจากคลัง → พิมพ์แบบฟอร์ม PDF/Excel (ตามแบบ "
               "Autozone-แบบฟอร์มตรวจนับสต๊อก) → คีย์ยอดนับในจอ หรือนำเข้าจาก Excel → ปรับปรุงสต็อก",
    "description": """
ระบบตรวจนับสต็อก (Physical Count) จบในจอเดียว

* เลือกสาขา/คลัง → ดึงรายการสินค้าที่มีสต็อก จัดกลุ่มตามหมวด (เหมือนแบบฟอร์มกระดาษ)
* พิมพ์แบบฟอร์มตรวจนับ PDF หรือ Export Excel ไปให้สาขานับ (ปิดยอดคงเหลือได้ = blind count)
* คีย์ยอดนับในจอ Odoo (list แก้ได้) หรืออัปโหลดไฟล์ Excel ที่กรอกยอดแล้วกลับเข้ามา
* เห็นผลต่าง (จำนวน + มูลค่า) ก่อนอนุมัติ → กด "ปรับปรุงสต็อก" สร้าง Inventory Adjustment
  ลงวันที่ตามวันนับ (ย้อนหลังได้) และผูกรายการปรับปรุงกลับมาที่ใบนับ
    """,
    "depends": ["stock", "stock_account", "autozone_report_fonts", "autozone_base_address"],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "report/paperformat.xml",
        "report/stock_count_report.xml",
        "wizard/stock_count_import_views.xml",
        "views/stock_count_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
