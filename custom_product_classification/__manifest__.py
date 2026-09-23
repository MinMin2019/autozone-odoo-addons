{
    "name": "Autozone Product Classification",
    "version": "18.0.1.2.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "Classification fields on products (brand, sub-type, product owner, part, "
               "car make/model, tone, work type, work stage) with search panel, filters "
               "and group-by, so product categories only drive accounting.",
    "depends": ["product", "stock", "mail", "stock_account", "sale", "purchase", "account"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/master_data.xml",
        "views/master_views.xml",
        "views/product_template_views.xml",
        "views/report_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
