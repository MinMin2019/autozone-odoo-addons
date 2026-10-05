# -*- coding: utf-8 -*-
# v18.0.1.8.0 ปุ่ม "รับชำระเงิน" บนใบวางบิล
# เปิดหน้าต่าง Register Payment มาตรฐานของ Odoo กับใบแจ้งหนี้ที่ยังค้างในใบวางบิล
# ค่าเริ่มต้น = รวมเป็นใบรับเงินใบเดียว (ตรงกับที่ผ่านมา: ใบวางบิลทุกใบที่รับเงินแล้วรับเป็นก้อนเดียว)
# หัก ณ ที่จ่าย / Excess / ค่าธรรมเนียม ให้ผู้ใช้กรอกในหน้าต่างเหมือนรับเงินจากใบแจ้งหนี้ตามปกติ
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CustomerBillingNotePayment(models.Model):
    _inherit = 'customer.billing.note'

    bn_has_unpaid = fields.Boolean(compute='_compute_bn_payments')
    bn_payment_ids = fields.Many2many('account.payment', compute='_compute_bn_payments',
                                      string='ใบรับเงิน')
    bn_payment_count = fields.Integer(compute='_compute_bn_payments')

    def _bn_unpaid_invoices(self):
        self.ensure_one()
        return self.invoice_ids.filtered(
            lambda m: m.state == 'posted' and m.payment_state in ('not_paid', 'partial'))

    @api.depends('invoice_ids.payment_state', 'invoice_ids.matched_payment_ids')
    def _compute_bn_payments(self):
        for rec in self:
            invoices = rec.invoice_ids
            # matched_payment_ids = จ่ายผ่านหน้าต่าง Register Payment
            # ส่วนที่จับคู่ทีหลัง (reconcile มือ) ดูจากบรรทัดลูกหนี้
            receivable = invoices.line_ids.filtered(lambda l: l.account_type == 'asset_receivable')
            payments = invoices.matched_payment_ids | receivable.matched_credit_ids.credit_move_id.payment_id
            rec.bn_payment_ids = payments
            rec.bn_payment_count = len(payments)
            rec.bn_has_unpaid = bool(invoices.filtered(
                lambda m: m.state == 'posted' and m.payment_state in ('not_paid', 'partial')))

    def action_bn_register_payment(self):
        # เรียกได้ทั้งจากปุ่มบนฟอร์ม (1 ใบ) และเมนู Action ในหน้ารายการ (ติ๊กหลายใบ)
        # หลายใบต้องเป็นลูกค้าเดียวกัน: ต่างลูกค้า wizard จะแตกเป็นหลายใบรับเงิน
        # และแก้ยอด/หัก ณ ที่จ่ายในหน้าต่างไม่ได้
        not_confirmed = self.filtered(lambda b: b.state not in ('confirmed', 'done'))
        if not_confirmed:
            raise UserError(_('ต้องกด Confirm ใบวางบิลก่อน จึงจะรับชำระเงินได้: %s')
                            % ', '.join(not_confirmed.mapped('name')))
        if len(self.partner_id.commercial_partner_id) > 1:
            raise UserError(_('รับชำระหลายใบวางบิลพร้อมกันได้เฉพาะลูกค้ารายเดียวกัน'))
        invoices = self.env['account.move']
        for rec in self:
            invoices |= rec._bn_unpaid_invoices()
        if not invoices:
            raise UserError(_('ใบแจ้งหนี้ในใบวางบิลที่เลือกชำระครบแล้ว'))
        notes = self.filtered(lambda b: b._bn_unpaid_invoices())
        return {
            'name': _('รับชำระเงิน %s') % ', '.join(notes.mapped('name')),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': invoices.ids,
                'default_group_payment': True,
                'bn_choose_journal': True,
            },
        }

    def action_bn_view_payments(self):
        self.ensure_one()
        payments = self.bn_payment_ids
        action = {
            'name': _('ใบรับเงิน'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'context': {'create': False},
        }
        if len(payments) == 1:
            action.update(view_mode='form', res_id=payments.id)
        else:
            action.update(view_mode='list,form', domain=[('id', 'in', payments.ids)])
        return action


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.depends('payment_type', 'company_id', 'can_edit_wizard')
    def _compute_available_journal_ids(self):
        # เปิดจากใบวางบิล: ให้เลือกได้เฉพาะสมุดรับเงิน (รหัสขึ้นต้น RV: RVB1-8 ธนาคาร, RVC เงินสด)
        # กันเลือกสมุดจ่าย PV / เงินสดย่อย PC แล้วได้เลขใบแปลก ๆ (เช่น PAY2026/09/...)
        super()._compute_available_journal_ids()
        if self.env.context.get('bn_choose_journal'):
            for wizard in self:
                receipt = wizard.available_journal_ids.filtered(lambda j: (j.code or '').upper().startswith('RV'))
                wizard.available_journal_ids = receipt or wizard.available_journal_ids

    @api.depends('available_journal_ids')
    def _compute_journal_id(self):
        # เปิดจากใบวางบิล: ไม่เติมสมุดรับเงินให้ ให้พนักงานเลือกบัญชีที่เงินเข้าจริงเอง
        # (ค่าตั้งต้นของ Odoo = RVB1 ซึ่งแทบไม่ได้ใช้ เคยทำให้เลขใบรับเงินซ้ำ RVB8)
        # ช่อง Journal ในหน้าต่างเป็น required อยู่แล้ว ไม่เลือกจะบันทึกไม่ได้
        if not self.env.context.get('bn_choose_journal'):
            return super()._compute_journal_id()
        for wizard in self:
            if wizard.journal_id not in wizard.available_journal_ids:
                wizard.journal_id = False

    def _bn_fill_without_journal(self):
        # core ไม่คำนวณยอด/โหมดงวดจนกว่าจะมีสมุด → เปิดจากใบวางบิลให้ยอดขึ้นทันที
        # (สกุลเงินตกไปใช้ของใบแจ้งหนี้/บริษัท ซึ่งคือ THB เหมือนสมุดทุกเล่ม)
        if not self.env.context.get('bn_choose_journal'):
            return self.browse()
        return self.filtered(lambda w: not w.journal_id and w.currency_id and w.payment_date)

    @api.depends('can_edit_wizard', 'source_amount', 'source_amount_currency', 'source_currency_id',
                 'company_id', 'currency_id', 'payment_date', 'installments_mode')
    def _compute_amount(self):
        todo = self._bn_fill_without_journal().filtered(lambda w: not w.custom_user_amount)
        for wizard in todo:
            wizard.amount = wizard._get_total_amounts_to_pay(wizard.batches)['amount_by_default']
        return super(AccountPaymentRegister, self - todo)._compute_amount()

    @api.depends('amount')
    def _compute_installments_mode(self):
        todo = self._bn_fill_without_journal()
        for wizard in todo:
            totals = wizard._get_total_amounts_to_pay(wizard.batches)
            if wizard.currency_id.compare_amounts(wizard.amount, totals['full_amount']) == 0:
                wizard.installments_mode = 'full'
            elif wizard.currency_id.compare_amounts(wizard.amount, totals['amount_by_default']) == 0:
                wizard.installments_mode = totals['installment_mode']
            else:
                wizard.installments_mode = 'full'
        return super(AccountPaymentRegister, self - todo)._compute_installments_mode()

    def action_create_payments(self):
        if self.env.context.get('bn_choose_journal') and not self.journal_id:
            raise UserError(_('กรุณาเลือก Journal (บัญชีที่เงินเข้าจริง) ก่อนบันทึกรับชำระ'))
        return super().action_create_payments()
