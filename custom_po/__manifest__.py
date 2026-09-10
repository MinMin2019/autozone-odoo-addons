{
    "name": "Custom Purchase Order (External Layout)",
    "version": "18.0.1.1.0",
    "category": "Autozone/Purchase",
    'author': 'Autozone',
    "summary": "Center company address and force single-line address in report header (external layout).",
    "depends": ["web", "purchase", "autozone_base_address"],
    "data": [
        "views/res_users_views.xml",
        "views/purchase_order_views.xml",
        "views/report_external_layout_inherit.xml",
        "views/report_purchase_order_body.xml",
        "views/report_purchase_quotation_body.xml"
    ],
    "installable": True,
    "application": False,
}