{
    "name": "Stock Backdate",
    "version": "18.0.1.3.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "Validate a transfer with a backdated actual date, and repair the date of transfers already validated with the wrong one.",
    "depends": ["stock_account", "account"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/stock_backdate_fix_views.xml",
        "wizard/stock_backdate_bulk_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
