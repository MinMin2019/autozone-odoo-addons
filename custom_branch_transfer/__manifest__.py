{
    "name": "Autozone Branch Transfer (H.O. <-> Branch)",
    "version": "18.0.1.4.2",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "ใบโอนสินค้าไปสาขา (BT: ส่วนกลางส่ง สาขารับ, TOUT/TIN) + สาขาโอนคืนส่วนกลาง "
               "(BR: สาขาส่ง ส่วนกลางรับ, ROUT/RIN) จบในจอเดียว + กันสร้างใบมือ + กันรับก่อนส่ง",
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
