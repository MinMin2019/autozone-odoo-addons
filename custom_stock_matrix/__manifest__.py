{
    "name": "Stock Matrix (สินค้า × สาขา)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "ตารางสินค้า × สาขา หน้าเดียว ณ วันที่: จำนวน/มูลค่า ทุกสาขาเรียงเป็นคอลัมน์ + รวมแถว/รวมคอลัมน์ + Excel/PDF",
    "description": """
Stock Matrix ตามมาตรฐาน ERP: มองภาพรวมว่าสินค้าแต่ละตัวอยู่สาขาไหนเท่าไหร่ในหน้าเดียว

* ยอดคงเหลือ ณ วันที่ ต่อสินค้าต่อสาขา (จำนวน / มูลค่า / ต้นทุน)
* หน้าจอ pivot: แถว = สินค้า, คอลัมน์ = สาขา, รวมท้ายแถวและท้ายคอลัมน์ (สลับ จำนวน/มูลค่า, ย่อ/ขยายหมวด)
* Excel: ตารางจริง 2 ชีท (จำนวน / มูลค่า) + ชีทข้อมูลดิบ
* PDF แนวนอน แบ่งสาขาเป็นชุดละ 13 คอลัมน์
* คอลัมน์เสริม: จำนวนสาขาที่มีของ, ยอดรวม, สาขาที่มีมากสุด/น้อยสุด
    """,
    "depends": ["stock", "stock_account", "autozone_report_fonts"],
    "data": [
        "security/ir.model.access.csv",
        "report/stock_matrix_report.xml",
        "wizard/stock_matrix_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
