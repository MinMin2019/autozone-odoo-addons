# -*- coding: utf-8 -*-
"""สร้าง record rule ขอบเขตคลังตอนติดตั้ง (โครงเดียวกับ custom_branch_transfer)

* มี custom_warehouse_scope: ใช้ allowed_warehouse_ids / warehouse_unrestricted
* ไม่มี: ใช้ Default Warehouse (res.users.property_warehouse_id) — ไม่ได้ตั้ง = เห็นทุกใบ
"""

DOMAIN_SCOPE = (
    "[(1, '=', 1)] if (user.warehouse_unrestricted or not user.allowed_warehouse_ids) else "
    "[('{w}', 'in', user.allowed_warehouse_ids.ids)]"
)
DOMAIN_STD = (
    "[(1, '=', 1)] if not user.property_warehouse_id else "
    "[('{w}', '=', user.property_warehouse_id.id)]"
)


def post_init_hook(env):
    scope_installed = bool(
        env["ir.module.module"].search_count(
            [("name", "=", "custom_warehouse_scope"), ("state", "in", ("installed", "to install", "to upgrade"))]
        )
    )
    tmpl = DOMAIN_SCOPE if scope_installed else DOMAIN_STD
    rules = [
        ("rule_az_stock_count_wh_scope", "az.stock.count", "warehouse_id"),
        ("rule_az_stock_count_line_wh_scope", "az.stock.count.line", "count_id.warehouse_id"),
    ]
    for xmlid, model, w in rules:
        vals = {
            "name": "Warehouse scope: %s" % model,
            "model_id": env["ir.model"]._get_id(model),
            "domain_force": tmpl.format(w=w),
            "global": True,
        }
        rule = env.ref("custom_stock_count.%s" % xmlid, raise_if_not_found=False)
        if rule:
            rule.write(vals)
        else:
            rule = env["ir.rule"].create(vals)
            env["ir.model.data"]._update_xmlids(
                [{"xml_id": "custom_stock_count.%s" % xmlid, "record": rule, "noupdate": True}]
            )
