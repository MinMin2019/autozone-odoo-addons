{
    "name": "Autozone Audit Log",
    "version": "18.0.3.0.0",
    "category": "Autozone/Tools",
    "author": "Autozone",
    "summary": "Audit trail: log deletions/archives with data snapshot, login attempts with IP, "
    "module install/upgrade history, daily menu usage per user, "
    "and chatter-track sensitive fields "
    "(bank accounts, prices, payment terms, credit limit).",
    "depends": ["base", "web", "account"],
    "data": [
        "security/ir.model.access.csv",
        "views/delete_log_views.xml",
        "views/menu_usage_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
