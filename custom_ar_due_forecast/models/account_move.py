# -*- coding: utf-8 -*-
"""ข้อมูลใบวางบิลบนใบแจ้งหนี้ (ไม่ store) สำหรับหน้ารายการที่เปิดจากรายงานคาดรับเงินลูกหนี้"""
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    ar_billing_note = fields.Char("เลขใบวางบิล", compute="_compute_ar_billing")
    ar_billing_date = fields.Date("วันที่วางบิล", compute="_compute_ar_billing")
    ar_promise_date = fields.Date("วันนัดรับชำระ", compute="_compute_ar_billing")
    ar_expected_date = fields.Date(
        "วันคาดรับ", compute="_compute_ar_billing",
        help="วันนัดรับชำระในใบวางบิล ถ้าไม่ได้ใส่ ใช้วันครบกำหนดของใบแจ้งหนี้",
    )

    def _compute_ar_billing(self):
        bn = {}
        ids = [i for i in self.ids if isinstance(i, int)]
        if ids:
            self.env["customer.billing.note"].flush_model()
            self.env.cr.execute(
                """
                SELECT DISTINCT ON (r.move_id) r.move_id, b.name, b.date, b.promise_date
                  FROM billing_note_move_rel r
                  JOIN customer_billing_note b ON b.id = r.billing_id
                 WHERE b.state != 'cancel' AND r.move_id IN %s
                 ORDER BY r.move_id, b.date DESC, b.id DESC
                """,
                (tuple(ids),),
            )
            bn = {mid: (name, bdate, promise) for mid, name, bdate, promise in self.env.cr.fetchall()}
        for move in self:
            name, bdate, promise = bn.get(move.id, (False, False, False))
            move.ar_billing_note = name or False
            move.ar_billing_date = bdate or False
            move.ar_promise_date = promise or False
            move.ar_expected_date = promise or move.invoice_date_due
