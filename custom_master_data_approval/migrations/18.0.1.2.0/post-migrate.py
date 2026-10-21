import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # 1.2.0: ผู้อนุมัติ = รายชื่อ user บนประเภทการอนุมัติ ไม่ผูก role แล้ว
    # ถอดกลุ่มผู้อนุมัติออกจาก implied ของกลุ่ม role (ที่ 1.1.0 เคยเติมไว้)
    # ไม่งั้นกด Apply role ทีหลังจะยัดคนกลับเข้ากลุ่มเอง
    cr.execute("SELECT to_regclass('access_role')")
    if not cr.fetchone()[0]:
        return
    cr.execute("""
        DELETE FROM res_groups_implied_rel r
         USING ir_model_data d
         WHERE d.model = 'res.groups'
           AND d.module = 'custom_master_data_approval'
           AND d.name IN ('group_mda_approver_partner', 'group_mda_approver_product')
           AND r.hid = d.res_id
           AND r.gid IN (SELECT group_id FROM access_role WHERE group_id IS NOT NULL)
    """)
    _logger.info("MDA 1.2.0: removed %s role->approver implied links", cr.rowcount)
