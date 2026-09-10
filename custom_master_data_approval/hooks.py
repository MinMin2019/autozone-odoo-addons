import logging

_logger = logging.getLogger(__name__)

# ผูก role builder อัตโนมัติ: xmlid ประเภทการอนุมัติ -> code ของ access.role
ROLE_MAPPING = {
    "custom_master_data_approval.mda_type_partner": "as",   # หัวหน้าบัญชี
    "custom_master_data_approval.mda_type_product": "am",   # ผู้จัดการบัญชี
}


def post_init_hook(env):
    # 1) backfill: ข้อมูลเดิมทั้งหมดถือว่าอนุมัติแล้ว — ระบบเดินต่อไม่สะดุด
    #    (ตอนสร้างคอลัมน์ Odoo เติม default 'draft' ให้ทุกแถวก่อน จึงต้อง update ทับ)
    for table in ("res_partner", "product_template"):
        env.cr.execute(
            "UPDATE %s SET approval_state = 'approved'" % table)
        _logger.info("MDA backfill %s: %s rows approved", table, env.cr.rowcount)

    # 2) ผูก role ตาม code (role เป็น record ใน DB ไม่มี xmlid จึงอ้างด้วย code)
    Role = env["access.role"]
    for type_xmlid, role_code in ROLE_MAPPING.items():
        t = env.ref(type_xmlid, raise_if_not_found=False)
        role = Role.search([("code", "=", role_code)], limit=1)
        if t and role:
            t.approver_role_ids = [(4, role.id)]
            _logger.info("MDA linked role %s -> %s", role_code, t.name)
        elif t:
            _logger.warning(
                "MDA: ไม่พบ role code '%s' — ตั้ง Role ผู้อนุมัติเองที่เมนู "
                "อนุมัติข้อมูลหลัก > ประเภทการอนุมัติ", role_code)

    env["az.approval.type"].search([])._sync_role_implied()
