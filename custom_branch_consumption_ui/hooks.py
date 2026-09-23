# -*- coding: utf-8 -*-
"""record rule ขอบเขตคลังของใบเบิกใช้วัสดุ — โครงเดียวกับ custom_branch_transfer

ลำดับ: warehouse_unrestricted -> ทุกใบ; Allowed Warehouses (custom_warehouse_scope) ไม่ว่าง -> ตามนั้น;
ไม่งั้น Default Warehouse (res.users.property_warehouse_id); ไม่ได้ตั้งอะไรเลย -> เห็นทุกใบ
"""

DOMAIN_STD = (
    "[(1, '=', 1)] if not user.property_warehouse_id else "
    "[('{w}', '=', user.property_warehouse_id.id)]"
)
# มี warehouse_scope: unrestricted -> ทุกคลัง; Allowed Warehouses ไม่ว่าง -> ตามนั้น;
# ว่าง -> ถอยไปใช้ Default Warehouse เหมือน DOMAIN_STD
DOMAIN_SCOPE = (
    "[(1, '=', 1)] if user.warehouse_unrestricted else ("
    "[('{w}', 'in', user.allowed_warehouse_ids.ids)] if user.allowed_warehouse_ids else ("
    + DOMAIN_STD + "))"
)


def post_init_hook(env):
    scope_installed = bool(
        env["ir.module.module"].search_count(
            [("name", "=", "custom_warehouse_scope"),
             ("state", "in", ("installed", "to install", "to upgrade"))]
        )
    )
    tmpl = DOMAIN_SCOPE if scope_installed else DOMAIN_STD
    rules = [
        ("rule_az_branch_consumption_wh_scope", "az.branch.consumption", "warehouse_id"),
        ("rule_az_branch_consumption_line_wh_scope", "az.branch.consumption.line",
         "consumption_id.warehouse_id"),
    ]
    for xmlid, model, w in rules:
        vals = {
            "name": "Warehouse scope: %s" % model,
            "model_id": env["ir.model"]._get_id(model),
            "domain_force": tmpl.format(w=w),
            "global": True,
        }
        rule = env.ref("custom_branch_consumption_ui.%s" % xmlid, raise_if_not_found=False)
        if rule:
            rule.write(vals)
        else:
            rule = env["ir.rule"].create(vals)
            env["ir.model.data"]._update_xmlids(
                [{"xml_id": "custom_branch_consumption_ui.%s" % xmlid,
                  "record": rule, "noupdate": True}]
            )
