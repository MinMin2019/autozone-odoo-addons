{
    "name": "Custom Access Role Builder",
    "version": "18.0.1.0.0",
    "summary": "Build user access by clicking (role = a set of capability bricks)",
    "description": """
Access Role Builder
===================
Two-layer user access model:
  * Capability brick = one (model + access level + domain)
  * Role            = composed from bricks via implied_ids

The Apply button generates res.groups / ir.model.access / ir.rule automatically
(dedup + idempotent), builds a whitelist menu tree, and flags conflicts with
Odoo's standard groups.
    """,
    "author": "Autozone",
    "category": "Autozone/Access",
    "depends": [
        "base",
        "account",
        "sale_management",
        "purchase",
        "stock",
        "contacts",
    ],
    "data": [
        "security/access_security.xml",
        "security/ir.model.access.csv",
        "data/access_categories.xml",
        "data/foundation_data.xml",
        "data/generated_root_menu.xml",
        "views/access_catalog_views.xml",
        "views/access_role_views.xml",
        "views/access_role_transfer_views.xml",
        "views/menu.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
