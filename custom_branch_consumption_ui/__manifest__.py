{
    "name": "Autozone Branch Consumption Form (ใบเบิกใช้วัสดุ)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "ใบเบิกใช้วัสดุจอเดียว: เลือกสาขา + สินค้า/จำนวน แล้วกดบันทึกเบิก "
               "ระบบสร้างและ validate ใบ CONS ของสาขาให้เอง (ไม่ต้องผ่าน Inventory Overview)",
    "depends": ["custom_branch_consumption", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/branch_consumption_views.xml",
        "views/stock_picking_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
