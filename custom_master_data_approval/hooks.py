import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    # backfill: ข้อมูลเดิมทั้งหมดถือว่าอนุมัติแล้ว — ระบบเดินต่อไม่สะดุด
    # (ตอนสร้างคอลัมน์ Odoo เติม default 'draft' ให้ทุกแถวก่อน จึงต้อง update ทับ)
    # ผู้อนุมัติกำหนดเป็นรายชื่อ user ที่เมนู อนุมัติข้อมูลหลัก > ประเภทการอนุมัติ
    for table in ("res_partner", "product_template"):
        env.cr.execute(
            "UPDATE %s SET approval_state = 'approved'" % table)
        _logger.info("MDA backfill %s: %s rows approved", table, env.cr.rowcount)
