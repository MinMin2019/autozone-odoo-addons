{
    "name": "Purchase Line Report (Monthly)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Purchase",
    "author": "Autozone",
    "summary": "รายงานใบสั่งซื้อรายบรรทัดตามเดือน: เลข PO วันที่ ผู้ขาย สินค้า จำนวนสั่ง จำนวนรับแล้ว "
               "ราคาต่อหน่วย ยอดรวม ดูบนจอหรือ Export Excel",
    "depends": ["purchase"],
    "data": [
        "security/ir.model.access.csv",
        "views/purchase_line_report_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
