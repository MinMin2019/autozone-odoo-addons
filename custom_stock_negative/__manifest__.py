{
    "name": "Negative Stock Report (สต็อกติดลบ)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "รายงานสต็อกติดลบ ณ วันที่: ติดลบเท่าไหร่ ตั้งแต่เมื่อไหร่ เพราะเอกสารไหน มีของกำลังเข้ามาแก้ไหม + โหมดประวัติรายการที่ทำให้ติดลบ",
    "description": """
รายงานสต็อกติดลบ (Negative Stock) ตามมาตรฐาน ERP ที่ Odoo ไม่มีในตัว (ทำได้แค่กรอง quant)

* โหมด "ติดลบ ณ วันที่": สินค้า x สาขา (หรือตำแหน่ง) ที่ยอดคงเหลือ < 0
  จำนวน / มูลค่า / ติดลบตั้งแต่วันไหน / กี่วัน / เอกสารที่ทำให้ติดลบ (ประเภท + เลขที่) / ของค้างรับที่กำลังเข้ามา / คำแนะนำ
* โหมด "ประวัติรายการที่ทำให้ติดลบ": ทุกรายการจ่ายออกในช่วงวันที่ ที่ทำให้ยอดหลังจ่ายต่ำกว่า 0
  ใช้ดูว่ากระบวนการไหน (ส่งขาย / โอนออก / เบิกใช้) สร้างปัญหาบ่อย และใครทำ
* list / pivot / graph + PDF + Excel
    """,
    "depends": ["stock", "stock_account", "autozone_report_fonts"],
    "data": [
        "security/ir.model.access.csv",
        "report/stock_negative_report.xml",
        "wizard/stock_negative_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
