import re

from odoo import api, fields, models

# สมุดรับเงินลูกค้า = รหัสขึ้นต้น RV (RVB1-8 ธนาคาร, RVC เงินสด)
# ใบขายสดที่ใบรับเงินใช้เลขตาม: RCV (VAT, เลข CT...) / RCN (Non-VAT, เลข SR...)
MIRROR_JOURNALS = ('RCV', 'RCN')
RP_PREFIX = 'RP'
RP_LOCK_KEY = 8150000  # + YYMM -> pg_advisory_xact_lock key ต่อเดือน


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _az_is_customer_receipt(self):
        pay = self.origin_payment_id
        return bool(pay) and pay.payment_type == 'inbound' and pay.partner_type == 'customer' \
            and (self.journal_id.code or '').upper().startswith('RV')

    @api.model
    def _az_next_rp_name(self, date):
        """RP + YYMM + ลำดับ 3 หลัก นับต่อกันทุกสมุด (ต่อจากเลขที่พนักงานพิมพ์ไว้เดิมด้วย)"""
        yymm = date.strftime('%y%m')
        prefix = RP_PREFIX + yymm
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)', (RP_LOCK_KEY + int(yymm),))
        self.env.cr.execute(
            "SELECT name FROM account_move WHERE name ~ %s AND state != 'cancel'",
            ('^' + prefix + r'[0-9]{3,4}$',))
        last = max((int(n[len(prefix):]) for (n,) in self.env.cr.fetchall()), default=0)
        return '%s%03d' % (prefix, last + 1)

    def _az_receipt_name(self, docs):
        """เลขของใบรับเงินนี้ ตามเอกสารที่รับเงิน (docs = ใบขาย/ใบแจ้งหนี้ที่จะจับคู่)"""
        self.ensure_one()
        docs = docs.filtered(lambda m: m.name and m.name != '/')
        if len(docs) == 1 and docs.journal_id.code in MIRROR_JOURNALS:
            name = docs.name
            m = re.match(r'^[A-Za-z]+(\d{4})\d+$', name)
            same_month = m and m.group(1) == self.date.strftime('%y%m')
            taken = self.search_count([('journal_id', '=', self.journal_id.id), ('name', '=', name),
                                       ('state', '=', 'posted'), ('id', '!=', self.id)], limit=1)
            if same_month and not taken:
                return name
        return self._az_next_rp_name(self.date)

    def _get_starting_sequence(self):
        # ใบจ่าย/รับเงินใบแรกของสมุดใหม่: Odoo ตั้งเป็น "PPVB11/2026/00000" ซึ่งไม่เข้ากับ
        # sequence_override_regex (รหัสสมุด+ปี2หลัก+เดือน+ลำดับ) -> ได้เลขเพี้ยน
        # "PPVB11/2026/00None11None0001" แล้วยืนยันไม่ผ่าน (Duplicate สมุดจะติด regex มาด้วย)
        journal = self.journal_id
        is_payment = self.origin_payment_id or self.env.context.get('is_payment')
        if journal.sequence_override_regex and journal.payment_sequence and is_payment:
            move_date = self.date or self.invoice_date or fields.Date.context_today(self)
            return '%s%s000' % (journal.code, move_date.strftime('%y%m'))
        return super()._get_starting_sequence()

    def _post(self, soft=True):
        # ตั้งเลขก่อน post — ถ้ามีเลขอยู่แล้ว (พิมพ์เอง/เคย post) ไม่แตะ
        doc_map = self.env.context.get('az_receipt_docs') or {}
        for move in self:
            if (not move.name or move.name == '/') and move.date and move._az_is_customer_receipt():
                pay = move.origin_payment_id
                docs = self.browse(doc_map.get(pay.id) or doc_map.get(str(pay.id)) or []) or pay.invoice_ids
                move.name = move._az_receipt_name(docs)
        return super()._post(soft=soft)
