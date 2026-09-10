# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrEmployeeLoanPushWizard(models.TransientModel):
    _name = 'hr.employee.loan.push.wizard'
    _description = 'Push Loan Installments into Payslip Batch'

    payslip_run_id = fields.Many2one(
        'hr.payslip.run', string='Payslip Batch', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='payslip_run_id.currency_id')
    line_ids = fields.One2many(
        'hr.employee.loan.push.wizard.line', 'wizard_id', string='งวดที่จะหัก')
    skipped_note = fields.Text(string='รายการที่ข้าม', readonly=True)

    line_count = fields.Integer(compute='_compute_summary')
    employee_count = fields.Integer(compute='_compute_summary')
    total_principal = fields.Monetary(compute='_compute_summary', currency_field='currency_id')
    total_interest = fields.Monetary(compute='_compute_summary', currency_field='currency_id')
    total_amount = fields.Monetary(compute='_compute_summary', currency_field='currency_id')

    @api.depends('line_ids.amount', 'line_ids.amount_interest')
    def _compute_summary(self):
        for wizard in self:
            wizard.line_count = len(wizard.line_ids)
            wizard.employee_count = len(wizard.line_ids.mapped('employee_id'))
            wizard.total_principal = sum(wizard.line_ids.mapped('amount'))
            wizard.total_interest = sum(wizard.line_ids.mapped('amount_interest'))
            wizard.total_amount = wizard.total_principal + wizard.total_interest

    # ------------------------------------------------------------------
    # โหลดงวดที่ถึงกำหนดตอนเปิด wizard
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        batch_id = self.env.context.get('active_id')
        if self.env.context.get('active_model') != 'hr.payslip.run' or not batch_id:
            return res
        batch = self.env['hr.payslip.run'].browse(batch_id)
        # batch ที่มีสลิปจะเป็น 'verify' (Confirmed) โดยอัตโนมัติ — แก้ไขได้ทั้ง draft/verify
        if batch.state not in ('draft', 'verify'):
            raise UserError(_("หักเงินกู้ได้เฉพาะ Batch ที่ยังไม่ปิด (New/Confirmed) เท่านั้น"))
        if not batch.slip_ids:
            raise UserError(_("Batch นี้ยังไม่มีสลิป กรุณากด Generate Payslips ก่อน"))

        res['payslip_run_id'] = batch.id

        slip_map = {}
        for slip in batch.slip_ids:
            slip_map.setdefault(slip.employee_id.id, []).append(slip)

        # งวดที่ถึงกำหนด: เงินกู้กำลังผ่อน + งวดรอหัก + กำหนดหักไม่เกินวันสิ้นงวดของ Batch
        # รวมถึงงวดที่เคยดันเข้า Batch นี้แล้ว (จะถูกแทนที่ทั้งชุดตอนยืนยัน)
        due_lines = self.env['hr.employee.loan.line'].search([
            ('loan_id.state', '=', 'running'),
            ('company_id', '=', batch.company_id.id),
            ('date_due', '<=', batch.date_end),
            ('manual_paid', '=', False),
            '|',
            ('state', '=', 'open'),
            ('payslip_input_id.payslip_id.payslip_run_id', '=', batch.id),
        ], order='employee_id, date_due')

        skipped = []
        commands = []
        loan_line_model = self.env['hr.employee.loan.line']
        for line in due_lines:
            employee = line.loan_id.employee_id
            slips = slip_map.get(employee.id)
            if not slips:
                skipped.append(_("%s — ไม่มีสลิปใน Batch นี้ (งวดที่ %s ของ %s ยังคงสถานะรอหัก)")
                               % (employee.name, line.number, line.loan_id.name))
                continue
            if len(slips) > 1:
                skipped.append(_("%s — มีสลิปมากกว่า 1 ใบใน Batch ระบุอัตโนมัติไม่ได้")
                               % employee.name)
                continue
            slip = slips[0]
            if slip.state not in ('draft', 'verify'):
                skipped.append(_("%s — สลิปถูกยืนยันแล้ว แก้ไขไม่ได้") % employee.name)
                continue
            # กันหักซ้ำ: สลิปมี input LOAN/LOAN_INT ที่ไม่ได้มาจากทะเบียนเงินกู้
            # (เช่น มากับไฟล์ Excel)
            foreign = slip.input_line_ids.filtered(
                lambda i: i.input_type_id.code in ('LOAN', 'LOAN_INT')
                and not loan_line_model.search_count([
                    '|',
                    ('payslip_input_id', '=', i.id),
                    ('payslip_input_interest_id', '=', i.id)]))
            if foreign:
                skipped.append(_("%s — สลิปมีรายการหัก LOAN จากไฟล์ Excel/กรอกมืออยู่แล้ว "
                                 "(กันหักซ้ำ) ให้ลบรายการนั้นออกก่อน หรือเอาพนักงานออกจากไฟล์ import")
                               % employee.name)
                continue
            commands.append((0, 0, {
                'loan_line_id': line.id,
                'payslip_id': slip.id,
                'amount': line.amount,
                'amount_interest': line.amount_interest,
            }))

        if not commands and not skipped:
            raise UserError(_("ไม่มีงวดเงินกู้ที่ถึงกำหนดหักในช่วงของ Batch นี้"))
        res['line_ids'] = commands
        res['skipped_note'] = "\n".join(skipped) if skipped else False
        return res

    # ------------------------------------------------------------------
    # ยืนยัน — Replace เฉพาะ input LOAN ที่มาจากทะเบียนเงินกู้ใน Batch นี้
    # ------------------------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        batch = self.payslip_run_id
        if batch.state not in ('draft', 'verify'):
            raise UserError(_("Batch ถูกปิดไปแล้ว หักเงินกู้ไม่ได้"))
        if not self.line_ids:
            raise UserError(_("ไม่มีงวดให้หัก (ลบออกหมดแล้ว) — ปิดหน้าต่างนี้ได้เลย"))

        input_type = self.env.ref('import_payslip_inputs.input_type_loan')
        input_type_interest = self.env.ref('custom_hr_loan.input_type_loan_interest')
        loan_line_model = self.env['hr.employee.loan.line']

        for wline in self.line_ids:
            if wline.amount <= 0:
                raise UserError(_("เงินต้นของ %s ต้องมากกว่า 0 (ถ้าจะยกงวดนี้ ให้ลบแถวออก)")
                                % wline.employee_id.name)
            if wline.amount_interest < 0:
                raise UserError(_("ดอกเบี้ยของ %s ติดลบไม่ได้") % wline.employee_id.name)
            if wline.loan_line_id.manual_paid or wline.loan_line_id.state in ('paid', 'paid_manual'):
                raise UserError(_("งวดที่ %s ของ %s ถูกชำระไปแล้ว")
                                % (wline.loan_line_id.number, wline.employee_id.name))
            if wline.payslip_id.state not in ('draft', 'verify'):
                raise UserError(_("สลิปของ %s ถูกยืนยันไปแล้ว") % wline.employee_id.name)

        # 1) ล้าง input LOAN/LOAN_INT เดิมที่ "ทะเบียนเงินกู้" เคยดันเข้า Batch นี้
        #    (ไม่แตะของ Excel/กรอกมือ)
        editable_slips = batch.slip_ids.filtered(lambda s: s.state in ('draft', 'verify'))
        old_lines = loan_line_model.search([
            '|',
            ('payslip_input_id.payslip_id', 'in', editable_slips.ids),
            ('payslip_input_interest_id.payslip_id', 'in', editable_slips.ids)])
        # ondelete=set null → งวดกลับเป็นรอหัก
        (old_lines.mapped('payslip_input_id')
         | old_lines.mapped('payslip_input_interest_id')).unlink()

        # 2) ยอดที่แก้ในหน้าตัวอย่าง (เช่น ลดงวดเพราะเงินเดือนไม่พอ) เขียนกลับเข้าทะเบียน
        for wline in self.line_ids:
            currency = wline.loan_line_id.currency_id
            if currency.compare_amounts(wline.amount, wline.loan_line_id.amount) != 0:
                wline.loan_line_id.amount = wline.amount
            if currency.compare_amounts(
                    wline.amount_interest, wline.loan_line_id.amount_interest) != 0:
                wline.loan_line_id.amount_interest = wline.amount_interest

        # 3) รวมยอดต่อสลิป (พนักงานหนึ่งคนอาจมีหลายงวด/หลายสัญญา)
        #    → เงินต้นหนึ่ง input + ดอกเบี้ยหนึ่ง input (ถ้ามี) ต่อสลิป
        by_slip = {}
        for wline in self.line_ids:
            by_slip.setdefault(wline.payslip_id, []).append(wline)
        for slip, wlines in by_slip.items():
            principal_input = self.env['hr.payslip.input'].create({
                'payslip_id': slip.id,
                'input_type_id': input_type.id,
                'name': input_type.name,
                'amount': sum(w.amount for w in wlines),
            })
            interest_sum = sum(w.amount_interest for w in wlines)
            interest_input = False
            if interest_sum > 0:
                interest_input = self.env['hr.payslip.input'].create({
                    'payslip_id': slip.id,
                    'input_type_id': input_type_interest.id,
                    'name': input_type_interest.name,
                    'amount': interest_sum,
                })
            for wline in wlines:
                wline.loan_line_id.write({
                    'payslip_input_id': principal_input.id,
                    'payslip_input_interest_id': interest_input and interest_input.id,
                })

        slips = self.line_ids.mapped('payslip_id')
        slips.compute_sheet()

        body = Markup(
            "<b>หักเงินกู้พนักงานจากทะเบียนเงินกู้</b><ul>"
            "<li>พนักงาน: %s คน / %s งวด</li>"
            "<li>เงินต้น: %s / ดอกเบี้ย: %s / รวมยอดหัก: %s</li>"
            "<li>โหมด: ล้างรายการที่ทะเบียนเคยดันเข้า Batch นี้แล้วลงใหม่ทั้งชุด</li></ul>"
        ) % (self.employee_count, self.line_count,
             f"{self.total_principal:,.2f}", f"{self.total_interest:,.2f}",
             f"{self.total_amount:,.2f}")
        if self.skipped_note:
            body += Markup("<b>รายการที่ข้าม:</b><br/>%s") % Markup(
                "<br/>".join(escape(s) for s in self.skipped_note.splitlines()))
        batch.message_post(body=body)

        return {'type': 'ir.actions.client', 'tag': 'reload'}


class HrEmployeeLoanPushWizardLine(models.TransientModel):
    _name = 'hr.employee.loan.push.wizard.line'
    _description = 'Push Loan Wizard Preview Line'
    _order = 'employee_id, date_due'

    wizard_id = fields.Many2one(
        'hr.employee.loan.push.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    loan_line_id = fields.Many2one(
        'hr.employee.loan.line', string='งวดเงินกู้', required=True, ondelete='cascade')
    loan_id = fields.Many2one(related='loan_line_id.loan_id', string='เงินกู้')
    employee_id = fields.Many2one(related='loan_line_id.employee_id', string='พนักงาน')
    registration_number = fields.Char(
        related='employee_id.registration_number', string='รหัสพนักงาน')
    number = fields.Integer(related='loan_line_id.number', string='งวดที่')
    date_due = fields.Date(related='loan_line_id.date_due', string='กำหนดหัก')
    amount_remaining = fields.Monetary(
        related='loan_line_id.loan_id.amount_remaining', string='คงเหลือทั้งสัญญา')
    payslip_id = fields.Many2one('hr.payslip', string='สลิป', required=True)
    amount = fields.Monetary(
        string='เงินต้นงวดนี้',
        help="แก้ได้ถ้าเดือนนี้ต้องหักไม่เต็มงวด — ยอดใหม่จะถูกบันทึกกลับเข้าทะเบียนงวดด้วย")
    amount_interest = fields.Monetary(
        string='ดอกเบี้ยงวดนี้',
        help="แก้ได้ — ยอดใหม่จะถูกบันทึกกลับเข้าทะเบียนงวดด้วย")
    amount_total = fields.Monetary(
        string='รวมหักงวดนี้', compute='_compute_amount_total')

    @api.depends('amount', 'amount_interest')
    def _compute_amount_total(self):
        for line in self:
            line.amount_total = line.amount + line.amount_interest
