# -*- coding: utf-8 -*-
import math

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HrEmployeeLoan(models.Model):
    _name = 'hr.employee.loan'
    _description = 'Employee Loan (เงินกู้สวัสดิการพนักงาน)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_loan desc, id desc'

    # เลขที่: รันอัตโนมัติ LC<ปี พ.ศ.>/NNN จากวันที่จ่ายเงินกู้ (รีเซ็ตทุกปี)
    # แก้มือได้จนกว่าจะปิดยอด/ยกเลิก — ห้ามซ้ำในบริษัทเดียวกัน
    name = fields.Char(string='เลขที่', required=True, copy=False, tracking=True,
                       default=lambda self: _('New'))
    employee_id = fields.Many2one(
        'hr.employee', string='พนักงาน', required=True, tracking=True,
        domain="[('company_id', '=', company_id)]")
    registration_number = fields.Char(
        related='employee_id.registration_number', string='รหัสพนักงาน')
    department_id = fields.Many2one(
        related='employee_id.department_id', string='แผนก', store=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')

    date_loan = fields.Date(string='วันที่จ่ายเงินกู้', required=True,
                            default=fields.Date.context_today, tracking=True)
    principal_amount = fields.Monetary(string='เงินต้น', required=True, tracking=True)
    installment_amount = fields.Monetary(string='ยอดหักต่อเดือน', required=True, tracking=True)
    date_first_due = fields.Date(
        string='เดือนแรกที่เริ่มหัก', required=True, tracking=True,
        help="ระบบดูเฉพาะเดือน/ปี — งวดจะถึงกำหนดเมื่อวันนี้อยู่ในช่วงของ Payslip Batch")
    installment_count = fields.Integer(
        string='จำนวนงวด', compute='_compute_installment_count')

    interest_rate = fields.Float(
        string='ดอกเบี้ย (% ต่อปี)', digits=(5, 2), default=0.0, tracking=True,
        help="ใส่ 0 = ไม่คิดดอกเบี้ย ดอกเบี้ยจะถูกหักแยกบรรทัด (LOAN_INT) และลงบัญชีดอกเบี้ยรับ")
    interest_method = fields.Selection([
        ('flat', 'คงที่ (Flat — คิดจากเงินต้นเต็มทุกงวด)'),
        ('effective', 'ลดต้นลดดอก (คิดจากเงินต้นคงเหลือ)'),
    ], string='วิธีคิดดอกเบี้ย', default='flat', required=True, tracking=True)
    interest_total = fields.Monetary(
        string='ดอกเบี้ยรวมตามตาราง', compute='_compute_amounts', store=True)
    interest_received = fields.Monetary(
        string='ดอกเบี้ยรับแล้ว', compute='_compute_amounts', store=True)

    # JE จ่ายเงินกู้ลงมือในบัญชีตามปกติ ผูกไว้ที่นี่เพื่ออ้างอิง/กระทบยอดเท่านั้น
    move_id = fields.Many2one(
        'account.move', string='JE จ่ายเงินกู้ (อ้างอิง)', copy=False,
        domain="[('company_id', '=', company_id), ('move_type', '=', 'entry'), "
               "('state', '=', 'posted')]",
        groups='account.group_account_invoice')
    note = fields.Text(string='หมายเหตุ')

    line_ids = fields.One2many('hr.employee.loan.line', 'loan_id', string='งวดผ่อน', copy=False)
    amount_paid = fields.Monetary(
        string='หักแล้ว', compute='_compute_amounts', store=True)
    amount_remaining = fields.Monetary(
        string='คงเหลือ', compute='_compute_amounts', store=True)

    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('running', 'กำลังผ่อน'),
        ('done', 'ปิดยอดแล้ว'),
        ('cancel', 'ยกเลิก'),
    ], string='สถานะ', default='draft', required=True, copy=False, tracking=True)

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)',
         'เลขที่เงินกู้นี้มีอยู่แล้ว กรุณาใช้เลขอื่น'),
    ]

    @api.model
    def _next_loan_number(self, date_loan=None):
        """LC<ปี พ.ศ.>/NNN — ปีมาจากวันที่จ่ายเงินกู้, เลขรันรีเซ็ตทุกปี (date range)"""
        date_loan = fields.Date.to_date(date_loan) or fields.Date.context_today(self)
        number = self.env['ir.sequence'].with_context(
            ir_sequence_date=date_loan).next_by_code('hr.employee.loan')
        if not number:
            raise UserError(_("ไม่พบ sequence 'hr.employee.loan' — ติดตั้ง/อัปเกรดโมดูลอีกครั้ง"))
        return "LC%s/%s" % (date_loan.year + 543, number)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not (vals.get('name') or '').strip() or vals['name'] == _('New'):
                vals['name'] = self._next_loan_number(vals.get('date_loan'))
        return super().create(vals_list)

    @api.constrains('principal_amount', 'installment_amount', 'interest_rate')
    def _check_amounts(self):
        for loan in self:
            if loan.principal_amount <= 0:
                raise ValidationError(_("เงินต้นต้องมากกว่า 0"))
            if loan.installment_amount <= 0:
                raise ValidationError(_("ยอดหักต่อเดือนต้องมากกว่า 0"))
            if loan.installment_amount > loan.principal_amount:
                raise ValidationError(_("ยอดหักต่อเดือนต้องไม่เกินเงินต้น"))
            if loan.interest_rate < 0:
                raise ValidationError(_("อัตราดอกเบี้ยติดลบไม่ได้"))

    @api.depends('principal_amount', 'installment_amount')
    def _compute_installment_count(self):
        for loan in self:
            if loan.principal_amount > 0 and loan.installment_amount > 0:
                loan.installment_count = math.ceil(
                    loan.principal_amount / loan.installment_amount)
            else:
                loan.installment_count = 0

    @api.depends('principal_amount', 'line_ids.state', 'line_ids.amount',
                 'line_ids.amount_interest')
    def _compute_amounts(self):
        for loan in self:
            paid_lines = loan.line_ids.filtered(
                lambda l: l.state in ('paid', 'paid_manual'))
            loan.amount_paid = sum(paid_lines.mapped('amount'))
            loan.amount_remaining = loan.principal_amount - loan.amount_paid
            loan.interest_total = sum(loan.line_ids.mapped('amount_interest'))
            loan.interest_received = sum(paid_lines.mapped('amount_interest'))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_approve(self):
        """อนุมัติ + สร้างตารางงวดผ่อนอัตโนมัติ (งวดสุดท้าย = เศษที่เหลือ)

        ดอกเบี้ย: flat คิดจากเงินต้นเต็มทุกงวด / effective คิดจากเงินต้นคงเหลือ ณ ต้นงวด
        อัตราต่อเดือน = อัตราต่อปี / 12
        """
        for loan in self:
            if loan.state != 'draft':
                raise UserError(_("อนุมัติได้เฉพาะเงินกู้สถานะร่าง"))
            loan.line_ids.unlink()
            currency = loan.currency_id
            monthly_rate = loan.interest_rate / 100.0 / 12.0
            n = math.ceil(loan.principal_amount / loan.installment_amount)
            lines = []
            remaining = loan.principal_amount
            for i in range(n):
                amount = currency.round(min(loan.installment_amount, remaining))
                if monthly_rate:
                    base = loan.principal_amount if loan.interest_method == 'flat' else remaining
                    interest = currency.round(base * monthly_rate)
                else:
                    interest = 0.0
                lines.append({
                    'loan_id': loan.id,
                    'number': i + 1,
                    'date_due': loan.date_first_due + relativedelta(months=i),
                    'amount': amount,
                    'amount_interest': interest,
                })
                remaining -= amount
            self.env['hr.employee.loan.line'].create(lines)
            loan.state = 'running'
        return True

    def action_done(self):
        for loan in self:
            if loan.state != 'running':
                raise UserError(_("ปิดยอดได้เฉพาะเงินกู้ที่กำลังผ่อน"))
            if loan.currency_id.compare_amounts(loan.amount_remaining, 0) > 0:
                raise UserError(_(
                    "ยังมียอดคงเหลือ %s ปิดไม่ได้\n"
                    "ถ้าพนักงานโปะปิดยอด/หักจากเงินได้งวดสุดท้ายแล้ว ให้ติ๊ก 'ชำระเอง' "
                    "ที่งวดที่เหลือ (แก้ยอดงวดให้ตรงกับที่รับจริงได้) แล้วค่อยกดปิดยอด"
                ) % f"{loan.amount_remaining:,.2f}")
            loan.state = 'done'
        return True

    def action_cancel(self):
        for loan in self:
            blocked = loan.line_ids.filtered(lambda l: l.state != 'open')
            if blocked:
                raise UserError(_(
                    "ยกเลิกไม่ได้ — มีงวดที่หักแล้วหรือค้างอยู่ในสลิป (งวดที่ %s)\n"
                    "ถ้างวดค้างอยู่ในสลิปร่าง ให้ลบรายการหักออกจาก Batch ก่อน"
                ) % ", ".join(str(l.number) for l in blocked))
            loan.state = 'cancel'
        return True

    def action_draft(self):
        for loan in self:
            if loan.state not in ('running', 'cancel'):
                raise UserError(_("ดึงกลับเป็นร่างได้เฉพาะสถานะกำลังผ่อน/ยกเลิก"))
            blocked = loan.line_ids.filtered(lambda l: l.state != 'open')
            if blocked:
                raise UserError(_("ดึงกลับไม่ได้ — มีงวดที่หักแล้วหรือค้างอยู่ในสลิป"))
            loan.line_ids.unlink()
            loan.state = 'draft'
        return True

    def unlink(self):
        if any(loan.state not in ('draft', 'cancel') for loan in self):
            raise UserError(_("ลบได้เฉพาะเงินกู้สถานะร่างหรือยกเลิก"))
        return super().unlink()


class HrEmployeeLoanLine(models.Model):
    _name = 'hr.employee.loan.line'
    _description = 'Employee Loan Installment (งวดผ่อนเงินกู้)'
    _order = 'loan_id, date_due, number'

    loan_id = fields.Many2one(
        'hr.employee.loan', string='เงินกู้', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one(
        related='loan_id.employee_id', string='พนักงาน', store=True)
    company_id = fields.Many2one(related='loan_id.company_id', store=True)
    currency_id = fields.Many2one(related='loan_id.currency_id')

    number = fields.Integer(string='งวดที่', required=True)
    date_due = fields.Date(string='กำหนดหัก', required=True)
    amount = fields.Monetary(string='เงินต้น', required=True)
    amount_interest = fields.Monetary(string='ดอกเบี้ย', default=0.0)
    amount_total = fields.Monetary(
        string='รวมหักงวดนี้', compute='_compute_amount_total', store=True)

    # ผูกกับ Other Input ที่ถูกดันเข้าสลิป — ถ้าสลิป/Batch ถูกลบ ค่านี้ว่างเอง
    # แล้วงวดกลับมาเป็น "รอหัก" โดยอัตโนมัติ (ไม่ต้อง hook อะไรของ core)
    # เงินต้นกับดอกเบี้ยเป็น input คนละตัว (LOAN / LOAN_INT) เพื่อแยกบัญชีตอนลง JE
    payslip_input_id = fields.Many2one(
        'hr.payslip.input', string='Payslip Input', ondelete='set null', copy=False)
    payslip_input_interest_id = fields.Many2one(
        'hr.payslip.input', string='Payslip Input (ดอกเบี้ย)',
        ondelete='set null', copy=False)
    payslip_id = fields.Many2one(
        related='payslip_input_id.payslip_id', string='สลิปเงินเดือน', store=True)

    @api.depends('amount', 'amount_interest')
    def _compute_amount_total(self):
        for line in self:
            line.amount_total = line.amount + line.amount_interest

    manual_paid = fields.Boolean(
        string='ชำระเอง', copy=False,
        help="ติ๊กเมื่อรับชำระนอกระบบเงินเดือน เช่น โปะปิดยอด หักจากเงินได้งวดสุดท้ายตอนลาออก "
             "(แก้ยอดงวดให้ตรงกับที่รับจริงก่อนติ๊ก)")
    manual_note = fields.Char(string='หมายเหตุชำระเอง', copy=False)

    state = fields.Selection([
        ('open', 'รอหัก'),
        ('in_slip', 'อยู่ในสลิป'),
        ('paid', 'หักแล้ว'),
        ('paid_manual', 'ชำระเอง'),
    ], string='สถานะ', compute='_compute_state', store=True)

    @api.depends('manual_paid', 'payslip_input_id', 'payslip_input_id.payslip_id.state')
    def _compute_state(self):
        for line in self:
            slip = line.payslip_input_id.payslip_id
            if line.manual_paid:
                line.state = 'paid_manual'
            elif slip and slip.state in ('done', 'paid'):
                line.state = 'paid'
            elif slip and slip.state in ('draft', 'verify'):
                line.state = 'in_slip'
            else:
                line.state = 'open'

    @api.constrains('amount', 'amount_interest')
    def _check_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_("เงินต้นงวดต้องมากกว่า 0 (งวดที่ %s)") % line.number)
            if line.amount_interest < 0:
                raise ValidationError(_("ดอกเบี้ยงวดติดลบไม่ได้ (งวดที่ %s)") % line.number)

    def unlink(self):
        if any(line.state not in ('open',) for line in self):
            raise UserError(_("ลบได้เฉพาะงวดสถานะรอหัก"))
        return super().unlink()
