from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """คำนวณ 'ยอดจ่ายบิลตั้งหนี้' ใหม่ทุกใบ

    สูตรเดิมใช้ยอดค้างชำระล้วน พอ compute ถูกเรียกใหม่หลังบิลถูกจ่าย
    (residual = 0) ยอดจึงหายไป ทำให้ทะเบียนกอง/ใบขอเติมเงินต่ำกว่าจริง
    v1.6.0 เปลี่ยนสูตรแล้ว — ของเก่าต้องคำนวณใหม่ให้ตรง
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    clearings = env["petty.cash.clearing"].with_context(active_test=False).search([])
    if clearings:
        clearings._compute_amount_existing()
        clearings._compute_amounts()
        env.flush_all()
    replenishes = env["petty.cash.replenish"].with_context(active_test=False).search([])
    if replenishes:
        replenishes._compute_amount()
        env.flush_all()
