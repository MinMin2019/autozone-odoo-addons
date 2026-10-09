from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """คงยอดเดิมของใบขอเติมเงินที่ "เติมเงินแล้ว" ก่อน v1.10.2

    v1.10.2 เปลี่ยนสูตรยอดขอเติมเงินเป็นเงินสดจ่ายสุทธิ (หลังหัก ณ ที่จ่าย)
    ตอน upgrade Odoo คำนวณ amount_total ของทุกใบใหม่ (เพราะ compute เดียวกัน
    เติมฟิลด์ใหม่ amount_spent_total/amount_wht_total ด้วย) ใบที่เติมเงินไปแล้ว
    ด้วยยอดเต็มจึงถูกเปลี่ยนเป็นยอดสุทธิ ทั้งที่เงินจ่ายไปแล้วจริงตามยอดเต็ม

    ตามที่ตกลง (9 ต.ค. 2569): ใบเก่าที่เติมเงินแล้วให้แสดงเหมือนเดิมทุกประการ
    → amount_total กลับเป็นยอดเต็ม และ amount_wht_total = 0 เพื่อให้ฟอร์มพิมพ์
    ไม่แสดงคอลัมน์/บรรทัดหัก ณ ที่จ่าย (เงินเติมเกินของใบพวกนี้บัญชีเก็บกวาดแยก)
    ใบที่ยังเป็นร่างใช้สูตรใหม่
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    done = env["petty.cash.replenish"].search([("state", "in", ("done", "cancel"))])
    if not done:
        return
    cr.execute(
        """
        UPDATE petty_cash_replenish
           SET amount_total = amount_spent_total,
               amount_wht_total = 0
         WHERE id IN %s
        """,
        (tuple(done.ids),),
    )
    env.invalidate_all()
