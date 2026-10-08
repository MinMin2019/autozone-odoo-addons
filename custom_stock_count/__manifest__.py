{
    "name": "Autozone Stock Count Sheet (ใบตรวจนับสต็อก)",
    "version": "18.0.1.1.3",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "ใบตรวจนับสต็อกประจำสาขา: ดึงรายการจากคลัง → พิมพ์แบบฟอร์ม PDF/Excel (ตามแบบ "
               "Autozone-แบบฟอร์มตรวจนับสต๊อก) → คีย์ยอดนับในจอ หรือนำเข้าจาก Excel → ปรับปรุงสต็อก",
    "description": """
ระบบตรวจนับสต็อก (Physical Count) จบในจอเดียว

* เลือกสาขา/คลัง → ดึงรายการสินค้าที่มีสต็อก จัดกลุ่มตามหมวด (เหมือนแบบฟอร์มกระดาษ)
* พิมพ์แบบฟอร์มตรวจนับ PDF หรือ Export Excel ไปให้สาขานับ (ปิดยอดคงเหลือได้ = blind count)
* คีย์ยอดนับในจอ Odoo (list แก้ได้) หรืออัปโหลดไฟล์ Excel ที่กรอกยอดแล้วกลับเข้ามา
* กระทบยอด: ยอดตามบัญชี ณ วันตัดยอด + รับเข้า - จ่ายออก (Odoo ดึงให้) = ยอดที่ควรมี ณ วันนับ
  ผลต่าง จำนวน / % / มูลค่า / สถานะ ขาด-เกิน-ตรง + บันทึกสาเหตุ/เอกสาร/ผู้รับผิดชอบ/การแก้ไขที่ต้นทาง
* ปิดใบได้ 2 ทาง: "ปิดใบ ไม่ปรับระบบ" (ค่าเริ่มต้น แก้ที่ต้นทาง) หรือ Inventory Manager กด "ปรับปรุงสต็อก"
  สร้าง Inventory Adjustment เท่าผลต่าง ลงวันที่ตามวันนับ และผูกรายการปรับปรุงกลับมาที่ใบนับ
* Excel 4 ชีต (ใบตรวจนับ / กระทบยอด / หมายเหตุผลต่าง / วิธีใช้) ตามแบบฟอร์ม v3 มีสูตรใช้ต่อได้เอง
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
