{
    "name": "Warehouse Scope (per-user)",
    "version": "18.0.1.0.0",
    "summary": "Restrict stock data per user by allowed warehouses (record-rule based)",
    "description": """
Warehouse Scope
===============
Data-minimization for stock by branch/warehouse — orthogonal to the document-type
dimension handled by roles.

  * res.users.allowed_warehouse_ids  = warehouses a user may see stock/operations for
  * res.users.warehouse_unrestricted = bypass (HQ / central staff / admin)

Global record rules scope stock.quant / stock.picking / stock.move(.line) to the
user's allowed warehouses. Warehouse & location MASTER records stay readable so
users can still transact WITH other warehouses (e.g. central) without seeing their
on-hand stock.

Rollout-safe: a user with NO allowed warehouses is NOT scoped (sees all) until you
assign warehouses to them.
    """,
    "author": "Autozone",
    "category": "Autozone/Access",
    "depends": ["stock"],
    "data": [
        "security/stock_record_rules.xml",
        "views/res_users_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
