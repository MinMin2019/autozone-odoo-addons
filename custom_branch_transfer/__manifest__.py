{
    "name": "Autozone Branch Transfer (H.O. -> Branch)",
    "version": "18.0.1.1.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "ใบโอนสินค้าไปสาขา: ส่วนกลางสร้าง/ส่ง สาขากดรับ — ครอบ Flow B (TOUT/TIN) ให้จบในจอเดียว "
               "+ กันสร้าง TOUT/TIN มือ + กันรับก่อนส่ง",
    "depends": ["stock", "autozone_base_address"],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "report/paperformat.xml",
        "report/branch_transfer_report.xml",
        "views/branch_transfer_views.xml",
        "views/stock_picking_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
