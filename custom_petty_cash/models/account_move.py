from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    petty_clearing_id = fields.Many2one(
        "petty.cash.clearing", string="ใบเคลียร์เงินสดย่อย",
        readonly=True, copy=False, index="btree_not_null")
    petty_existing_clearing_ids = fields.Many2many(
        "petty.cash.clearing", "petty_clearing_existing_bill_rel",
        "move_id", "clearing_id", string="ถูกดึงเข้าใบเคลียร์",
        help="ใบเคลียร์เงินสดย่อยที่ดึงบิลใบนี้ไปจ่ายแล้ว — "
        "ใช้กรองไม่ให้ดึงบิลเดียวกันซ้ำหลายใบ (ยอดกองจะถูกนับสองครั้ง)")
    petty_wht_amount = fields.Monetary(
        string="หัก ณ ที่จ่าย", compute="_compute_petty_wht_amount",
        currency_field="currency_id",
        help="ยอด WHT ที่จะถูกหักตอนจ่ายบิลใบนี้ (คำนวณจาก wht_tax_id บนบรรทัดบิล) — "
        "แสดงเพื่อทราบ การหักจริงเกิดตอน register payment")

    @api.depends("line_ids.wht_tax_id", "line_ids.amount_currency")
    def _compute_petty_wht_amount(self):
        # l10n_th_account_tax เก็บ WHT ไว้รายบรรทัดบิล แต่ไม่มีฟิลด์ยอดรวมระดับใบ
        # (มีแต่ has_wht) — รวมเองแยกตามอัตราของแต่ละบรรทัด
        # WHT แบบ PIT ใช้อัตราก้าวหน้า คำนวณตอนจ่ายจริง จึงไม่รวมมาแสดง
        for move in self:
            total = 0.0
            wht_lines = move.line_ids.filtered(
                lambda line: line.wht_tax_id and not line.wht_tax_id.is_pit)
            for tax in wht_lines.mapped("wht_tax_id"):
                base = sum(
                    wht_lines.filtered(lambda line, t=tax: line.wht_tax_id == t)
                    .mapped("amount_currency"))
                total += base * tax.amount / 100.0
            total = abs(total)
            move.petty_wht_amount = (
                move.currency_id.round(total) if move.currency_id else total)

    def _fetch_duplicate_reference(self, matching_states=("draft", "posted")):
        # แพตช์บั๊ก Odoo core (account_move.py `_fetch_duplicate_reference`):
        # โค้ดเดิมเข้าใจว่าตอนเรคคอร์ดยังไม่ถูกบันทึก (NewId) จะมีแค่ใบเดียว จึงอ่าน
        # moves[field_name] ตรง ๆ — ถ้ามีหลายใบพร้อมกัน m2o จะคืนหลายเรคคอร์ด
        # แล้ว convert_to_write เรียก .id → ValueError "Expected singleton"
        # เกิดตอน onchange ของใบเคลียร์ที่แท็บ "จ่ายบิลตั้งหนี้" มีบิลตั้งแต่ 2 ใบขึ้นไป
        # (ORM คำนวณ duplicated_ref_ids แบบ batch ทั้ง prefetch set)
        # → แยกคำนวณทีละใบเฉพาะกรณีนั้น ผลลัพธ์เหมือนเดิมทุกประการ
        if len(self) > 1 and not self[0].id:
            result = {}
            for move in self:
                result.update(
                    super(AccountMove, move)._fetch_duplicate_reference(matching_states))
            return result
        return super()._fetch_duplicate_reference(matching_states)
