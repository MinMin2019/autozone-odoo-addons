{
    "name": "ABC Analysis (จัดชั้นสินค้า A/B/C)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "วิเคราะห์ ABC/Pareto จากมูลค่าที่ใช้ไป จำนวนที่ใช้ หรือมูลค่าคงเหลือ ในช่วงวันที่ ทั้งบริษัทหรือรายสาขา + บันทึกชั้นลงสินค้า",
    "description": """
รายงาน ABC Analysis ตามมาตรฐาน ERP

* เกณฑ์: มูลค่าที่ใช้ไป (ค่าเริ่มต้น) / จำนวนที่ใช้ / มูลค่าคงเหลือ ณ วันสิ้นช่วง
* เรียงจากมากไปน้อย สะสม % → A = ถึง 80%, B = ถึง 95%, C = ที่เหลือ (ตั้งเกณฑ์ได้)
* ระดับทั้งบริษัท (โอนระหว่างสาขาไม่นับเป็นการใช้) หรือรายสาขา
* ตาราง Pareto: จำนวนสินค้า / % รายการ / มูลค่า / % มูลค่า ต่อชั้น
* ปุ่ม "บันทึกชั้นลงสินค้า" เก็บ A/B/C + วันที่ ไว้ที่ตัวสินค้า (แท็บ Inventory) ใช้กรองสินค้าเพื่อวางรอบนับสต็อก
* list / pivot / graph + PDF + Excel
    """,
    "depends": ["stock", "stock_account", "autozone_report_fonts"],
    "data": [
        "security/ir.model.access.csv",
        "views/product_views.xml",
        "report/stock_abc_report.xml",
        "wizard/stock_abc_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
