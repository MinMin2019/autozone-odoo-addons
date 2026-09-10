{
    "name": "Stock Count Variance (ผลต่างตรวจนับ)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "รายงานผลต่างตรวจนับสต็อก: ยอดระบบ / ยอดนับ / ผลต่าง (จำนวน+มูลค่า) / ผู้นับ-ผู้ปรับ ทั้งที่รอปรับปรุงและที่ปรับปรุงแล้ว + PDF/Excel",
    "description": """
รายงานผลต่างตรวจนับ (Physical Count Variance) ตามมาตรฐาน ERP ที่ Odoo ไม่มีในตัว

* โหมด "รอปรับปรุง": รายการที่นับแล้ว (กรอก Counted Quantity) แต่ยังไม่กด Apply
  ให้บัญชี/ผู้จัดการตรวจมูลค่าผลต่างก่อนอนุมัติ + ตัวเลือกแสดงรายการที่ถึงกำหนดนับแต่ยังไม่นับ
* โหมด "ปรับปรุงแล้ว": ประวัติการปรับปรุงจากการนับ (stock.move ที่ is_inventory) ตามช่วงวันที่
  ระบบก่อนปรับ / ยอดนับ / ผลต่าง / มูลค่า / ผู้กด Apply / เหตุผล
* สรุปต่อสาขา: จำนวนรายการ, ขาด, เกิน, สุทธิ, ความแม่นยำ (% รายการที่ตรง)
* ไม่รวม Scrap (คนละเรื่องกับการนับ)
    """,
    "depends": ["stock", "stock_account", "autozone_report_fonts"],
    "data": [
        "security/ir.model.access.csv",
        "report/stock_count_variance_report.xml",
        "wizard/stock_count_variance_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
