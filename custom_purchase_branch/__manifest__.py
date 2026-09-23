{
    "name": "Autozone Purchase Branch (Analytic)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Purchase",
    "author": "Autozone",
    "summary": "ช่อง 'สาขา' บนหัว PO เติม analytic ให้ทุกบรรทัด + บังคับก่อนยืนยัน + คอลัมน์/ตัวกรอง/จัดกลุ่มสาขา "
               "บน list PO และบรรทัด PO + รายงาน 'ซื้อตามสาขา' (สินค้า x สาขา) + มิติสาขาใน Purchase Analysis",
    "depends": ["purchase", "analytic"],
    "data": [
        "views/purchase_order_views.xml",
        "views/purchase_order_line_views.xml",
        "report/purchase_report_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
