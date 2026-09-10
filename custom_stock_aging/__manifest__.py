{
    "name": "Stock Aging (อายุสินค้าคงคลัง)",
    "version": "18.0.1.0.2",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "อายุสินค้าคงเหลือ ณ วันที่ แบ่งช่วง 0-30/31-60/61-90/91-180/181-365/เกิน 365 วัน ต่อสินค้าต่อสาขา + วันที่เคลื่อนไหวล่าสุด + PDF/Excel",
    "description": """
รายงาน Stock Aging ตามมาตรฐาน ERP ที่ Odoo ไม่มีในตัว

* ยอดคงเหลือ ณ วันที่ ต่อสินค้าต่อสาขา (หรือต่อตำแหน่ง) คำนวณจาก stock.move.line เหมือน Stock Card
* ไล่ย้อนการรับเข้าล่าสุดของสาขานั้น (หลัก FIFO) ว่าของที่เหลือมาจากการรับครั้งไหน
  แล้วนับอายุจากวันรับเข้าถึงวันที่รายงาน แบ่ง 6 ช่วง ทั้งจำนวนและมูลค่า
* อายุนับใหม่เมื่อโอนเข้าสาขา (เป็นอายุที่ของนอนอยู่ในสาขานั้น) ยอดยกยอดตอน go-live นับจากวันยกยอด
* คอลัมน์รับเข้าล่าสุด / จ่ายออกล่าสุด / วันที่ไม่เคลื่อนไหว ใช้หา slow-moving ได้ทันที
* มูลค่า = จำนวน x ต้นทุนที่บันทึกกับการรับเข้าครั้งนั้น (valuation layer) ถ้าไม่มีใช้ต้นทุนปัจจุบัน
    """,
    "depends": ["stock", "stock_account", "autozone_report_fonts"],
    "data": [
        "security/ir.model.access.csv",
        "report/stock_aging_report.xml",
        "wizard/stock_aging_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
