# -*- coding: utf-8 -*-
"""สร้าง record rule ขอบเขตคลังตอนติดตั้ง — เลือก domain ตามว่ามี custom_warehouse_scope หรือไม่

* มี custom_warehouse_scope: ใช้ allowed_warehouse_ids / warehouse_unrestricted ของมัน
* ไม่มี (production ปัจจุบัน): ใช้ Default Warehouse (res.users.property_warehouse_id) —
  ผู้ใช้ที่ไม่ได้ตั้ง = เห็นทุกใบ
"""

DOMAIN_SCOPE = (
    "[(1, '=', 1)] if (user.warehouse_unrestricted or not user.allowed_warehouse_ids) else "
    "['|', ('{w}', 'in', user.allowed_warehouse_ids.ids), ('{s}', 'in', user.allowed_warehouse_ids.ids)]"
)
DOMAIN_STD = (
    "[(1, '=', 1)] if not user.property_warehouse_id else "
    "['|', ('{w}', '=', user.property_warehouse_id.id), ('{s}', '=', user.property_warehouse_id.id)]"
)


def post_init_hook(env):
    scope_installed = bool(
        env["ir.module.module"].search_count(
            # นับ 'to install' ด้วย: ตอนสั่ง -i พร้อมกัน โมดูลนี้อาจโหลดก่อน custom_warehouse_scope
            [("name", "=", "custom_warehouse_scope"), ("state", "in", ("installed", "to install", "to upgrade"))]
        )
    )
    tmpl = DOMAIN_SCOPE if scope_installed else DOMAIN_STD
    rules = [
        ("rule_az_branch_transfer_wh_scope", "az.branch.transfer", "warehouse_id", "source_warehouse_id"),
        ("rule_az_branch_transfer_line_wh_scope", "az.branch.transfer.line",
         "transfer_id.warehouse_id", "transfer_id.source_warehouse_id"),
    ]
    for xmlid, model, w, s in rules:
        vals = {
            "name": "Warehouse scope: %s" % model,
            "model_id": env["ir.model"]._get_id(model),
            "domain_force": tmpl.format(w=w, s=s),
            "global": True,
        }
        rule = env.ref("custom_branch_transfer.%s" % xmlid, raise_if_not_found=False)
        if rule:
            rule.write(vals)
        else:
            rule = env["ir.rule"].create(vals)
            env["ir.model.data"]._update_xmlids(
                [{"xml_id": "custom_branch_transfer.%s" % xmlid, "record": rule, "noupdate": True}]
            )
