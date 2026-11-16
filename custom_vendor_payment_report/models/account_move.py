from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    vpr_amount_after_refund = fields.Monetary(
        string='ยอดหลังหักลดหนี้',
        compute='_compute_vpr_amount_after_refund',
        currency_field='currency_id',
        help='ยอดบิล หักด้วยใบลดหนี้ (Credit Note) ที่จับคู่ตัดกับบิลนี้แล้ว '
             '(ไม่หักการจ่ายเงินจริง จึงไม่กลายเป็น 0 หลังจ่าย)',
    )

    def _vpr_refund_offsets(self):
        """คืน list ของ (เอกสารคู่, ยอดที่จับคู่) เฉพาะคู่ที่เป็นบิล/ใบลดหนี้ฝั่ง AP
        เช่น บิลที่ถูก CN ตัดผ่านปุ่ม Credit Note บนบิล (CN จะ paid, บิลเป็น partial)
        การจ่ายเงิน (payment/entry) ไม่นับ"""
        self.ensure_one()
        res = []
        for line in self.line_ids.filtered(lambda l: l.display_type == 'payment_term'):
            for partial in line.matched_debit_ids:
                other = partial.debit_move_id.move_id
                if other != self and other.move_type in ('in_invoice', 'in_refund'):
                    # บรรทัดของเราเป็นฝั่ง credit -> ยอดในสกุลเงินของบิลเรา
                    res.append((other, partial.credit_amount_currency))
            for partial in line.matched_credit_ids:
                other = partial.credit_move_id.move_id
                if other != self and other.move_type in ('in_invoice', 'in_refund'):
                    res.append((other, partial.debit_amount_currency))
        return res

    @api.depends('amount_total', 'amount_residual')
    def _compute_vpr_amount_after_refund(self):
        for move in self:
            offset = sum(amount for _other, amount in move._vpr_refund_offsets()) \
                if move.move_type in ('in_invoice', 'in_refund') and move.state == 'posted' else 0.0
            move.vpr_amount_after_refund = move.amount_total - offset
