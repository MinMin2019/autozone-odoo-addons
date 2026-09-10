{
    "name": "Autozone Branch Material Consumption",
    "version": "18.0.1.3.1",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "Operation type 'เบิกใช้วัสดุ' per warehouse: consume branch materials to expense accounts "
               "(per product category) with branch analytic, replacing zero-price sale orders.",
    "depends": ["stock_account"],
    "data": [
        "data/stock_location_data.xml",
        "views/stock_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
