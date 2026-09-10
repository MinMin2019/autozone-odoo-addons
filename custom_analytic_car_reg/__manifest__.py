{
    "name": "Analytic Items: Car Registration",
    "version": "18.0.1.0.0",
    "category": "Autozone/Accounting",
    "author": "Autozone",
    "summary": "คอลัมน์ทะเบียนรถ (Car Registration) จากใบกำกับ/ใบแจ้งหนี้ "
               "ในรายการวิเคราะห์ (Analytic Items) พร้อมค้นหา/จัดกลุ่มได้",
    "depends": ["account", "custom_invoice_print", "custom_garage_receipt"],
    "data": [
        "views/account_analytic_line_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
