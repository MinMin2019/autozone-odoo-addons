{
    "name": "Payment Duplicate with Journal Items",
    "version": "18.0.1.0.0",
    "category": "Autozone/Accounting",
    "author": "Autozone",
    "summary": "คัดลอก Vendor/Customer Payment ไปเดือนใหม่พร้อมรายการบัญชีที่แก้ไว้ทั้งชุด (ใช้กับงานบันทึกเงินเดือนรายเดือน)",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/payment_duplicate_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
