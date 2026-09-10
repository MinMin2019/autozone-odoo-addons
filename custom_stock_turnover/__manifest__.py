{
    "name": "Inventory Turnover Report (อัตราหมุนเวียนสินค้า)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "อัตราหมุนเวียนสินค้า (รอบ/ปี) และวันที่ของค้างเฉลี่ย (Days of Inventory) ต่อบริษัท / สาขา / หมวด / สินค้า ในช่วงวันที่",
    "description": """
รายงานอัตราหมุนเวียนสินค้า (Inventory Turnover / Days of Inventory) ตามมาตรฐาน ERP

* ช่วงวันที่ → ยกมา / รับ / ใช้ไป (ส่งขาย-เบิกใช้-โอนออก) / ยกไป ทั้งจำนวนและมูลค่า
* มูลค่าเฉลี่ยที่ถือ = (ยกมา + ยกไป)/2 หรือเฉลี่ยจากยอดสิ้นเดือนทุกเดือนในช่วง
* Turnover (รอบ/ปี) = มูลค่าที่ใช้ไป ÷ มูลค่าเฉลี่ย ปรับเป็นรายปี
* Days of Inventory = 365 ÷ Turnover (ของนอนเฉลี่ยกี่วันก่อนถูกใช้)
* คำนวณครบ 4 ระดับในครั้งเดียว: ทั้งบริษัท / สาขา / หมวดสินค้า / สินค้า×สาขา (สลับด้วยฟิลเตอร์)
* list / pivot / graph + PDF + Excel
    """,
    "depends": ["stock", "stock_account", "autozone_report_fonts"],
    "data": [
        "security/ir.model.access.csv",
        "report/stock_turnover_report.xml",
        "wizard/stock_turnover_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
