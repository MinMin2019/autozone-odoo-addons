from odoo import models, fields, api, _
from odoo.exceptions import UserError

THAI_MONTHS = [
    'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
]


class VendorPaymentReport(models.Model):
    _name = 'vendor.payment.report'
    _description = 'Vendor Payment Report (รายงานการชำระเงิน)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # 1. ส่วนหัวของเอกสาร (Header)
    name = fields.Char(string='เลขที่รายงาน', required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))

    partner_id = fields.Many2one('res.partner', string='ผู้ขาย (Vendor)', required=True,
                                 domain=[('supplier_rank', '>', 0)])

    date = fields.Date(string='วันที่จัดทำ', default=fields.Date.context_today, required=True)

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    # ช่วงเวลาบนหัวรายงาน (เดือนไทย + พ.ศ.) — คำนวณจากวันที่บิล แก้มือทับได้
    period_display = fields.Char(
        string='ช่วงเวลา',
        compute='_compute_period_display', store=True, readonly=False,
    )

    @api.depends('bill_ids', 'bill_ids.invoice_date')
    def _compute_period_display(self):
        for record in self:
            dates = [d for d in record.bill_ids.mapped('invoice_date') if d]
            if not dates:
                record.period_display = False
                continue
            dmin, dmax = min(dates), max(dates)
            if (dmin.year, dmin.month) == (dmax.year, dmax.month):
                record.period_display = '%s %s' % (THAI_MONTHS[dmin.month - 1], dmin.year + 543)
            elif dmin.year == dmax.year:
                record.period_display = '%s-%s %s' % (
                    THAI_MONTHS[dmin.month - 1], THAI_MONTHS[dmax.month - 1], dmin.year + 543)
            else:
                record.period_display = '%s %s - %s %s' % (
                    THAI_MONTHS[dmin.month - 1], dmin.year + 543,
                    THAI_MONTHS[dmax.month - 1], dmax.year + 543)

    # =========================================================================
    # 2. ฟิลด์ Compute สำหรับกรองบิล (ป้องกันการเลือกซ้ำข้ามรายงาน)
    # =========================================================================
    available_bill_ids = fields.Many2many(
        'account.move',
        compute='_compute_available_bills'
    )

    @api.depends('partner_id')
    def _compute_available_bills(self):
        """กรอง Vendor Bill / Credit Note ของผู้ขายรายนี้ที่ posted ยังไม่จ่าย
        และยังไม่ถูกดึงไปเข้ารายงานการชำระเงินใบอื่น"""
        for record in self:
            if not record.partner_id:
                record.available_bill_ids = False
                continue

            domain_existing_reports = [
                ('partner_id', '=', record.partner_id.id),
                ('state', '!=', 'cancel'),
            ]
            if isinstance(record.id, int):
                domain_existing_reports.append(('id', '!=', record.id))

            existing_reports = self.env['vendor.payment.report'].search(domain_existing_reports)
            used_bill_ids = existing_reports.mapped('bill_ids').ids

            domain_bills = [
                ('partner_id', '=', record.partner_id.id),
                ('move_type', 'in', ['in_invoice', 'in_refund']),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['not_paid', 'partial']),
            ]

            if used_bill_ids:
                domain_bills.append(('id', 'not in', used_bill_ids))

            record.available_bill_ids = self.env['account.move'].search(domain_bills)

    # =========================================================================
    # 3. ความสัมพันธ์กับบิล (Many2many ตัวจริงที่จะแสดงหน้าจอ)
    # =========================================================================
    bill_ids = fields.Many2many(
        'account.move',
        'vendor_payment_report_move_rel',
        'report_id',
        'move_id',
        string='รายการบิล',
    )

    # 4. ยอดรวมและการคำนวณ (Computed Fields)
    amount_total = fields.Monetary(string='ยอดรวมบิล', compute='_compute_amounts', store=True)
    amount_wht = fields.Monetary(string='รวมหัก ณ ที่จ่าย', compute='_compute_amounts', store=True)
    amount_net = fields.Monetary(string='ยอดจ่ายสุทธิ', compute='_compute_amounts', store=True)

    # =========================================================================
    # 5. สถานะเอกสาร (State) - ระบบอัตโนมัติแบบเดียวกับใบวางบิลลูกค้า
    # =========================================================================
    is_confirmed = fields.Boolean(string='Is Confirmed', default=False, copy=False)
    is_cancelled = fields.Boolean(string='Is Cancelled', default=False, copy=False)

    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('confirmed', 'ยืนยัน'),
        ('done', 'ชำระแล้ว'),
        ('cancel', 'ยกเลิก')
    ], string='สถานะ', compute='_compute_state', store=True, tracking=True, default='draft')

    @api.depends('is_confirmed', 'is_cancelled', 'bill_ids.payment_state')
    def _compute_state(self):
        """คำนวณสถานะอัตโนมัติ โดยอิงจากการกดปุ่มและสถานะการจ่ายเงินของบิล"""
        for record in self:
            if record.is_cancelled:
                record.state = 'cancel'
            elif not record.is_confirmed:
                record.state = 'draft'
            else:
                if record.bill_ids:
                    all_paid = all(bill.payment_state in ['paid', 'in_payment', 'reversed']
                                   for bill in record.bill_ids)
                    record.state = 'done' if all_paid else 'confirmed'
                else:
                    record.state = 'confirmed'

    # ==========================
    # Logic & Methods (ฟังก์ชัน)
    # ==========================
    def _get_bill_wht(self, bill):
        """ยอดหัก ณ ที่จ่ายของบิล 1 ใบ (ยังไม่ติดเครื่องหมาย CN)
        คิดจากบรรทัดที่ติดธง WHT: ฐานก่อน VAT × อัตรา WHT (ข้าม PIT)"""
        wht = 0.0
        for line in bill.invoice_line_ids:
            tax = line.wht_tax_id
            if tax and not tax.is_pit:
                wht += line.price_subtotal * tax.amount / 100.0
        return bill.currency_id.round(wht)

    def _get_bill_amounts(self, bill):
        """คืน (ยอดบิล, หัก ณ ที่จ่าย, ยอดจ่ายสุทธิ) ติดเครื่องหมายลบถ้าเป็นใบลดหนี้"""
        sign = -1.0 if bill.move_type == 'in_refund' else 1.0
        amount = sign * bill.amount_total
        wht = sign * self._get_bill_wht(bill)
        return amount, wht, amount - wht

    def get_report_lines(self):
        """รายการบรรทัดสำหรับ QWeb report เรียงตามวันที่บิล เก่า→ใหม่"""
        self.ensure_one()
        lines = []
        bills = self.bill_ids.sorted(key=lambda b: (str(b.invoice_date or ''), b.name or ''))
        for bill in bills:
            amount, wht, net = self._get_bill_amounts(bill)
            lines.append({'bill': bill, 'amount': amount, 'wht': wht, 'net': net})
        return lines

    @api.depends('bill_ids', 'bill_ids.amount_total', 'bill_ids.invoice_line_ids.wht_tax_id')
    def _compute_amounts(self):
        for record in self:
            total = wht = 0.0
            for bill in record.bill_ids:
                amount, bill_wht, _net = record._get_bill_amounts(bill)
                total += amount
                wht += bill_wht
            record.amount_total = total
            record.amount_wht = wht
            record.amount_net = total - wht

    @api.model_create_multi
    def create(self, vals_list):
        """เจนเลขที่เอกสารตอนกด Save"""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('vendor.payment.report') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        """ปุ่มกดยืนยันรายงาน"""
        for record in self:
            if not record.bill_ids:
                raise UserError(_('กรุณาเลือกบิลอย่างน้อย 1 ใบ ก่อนกดยืนยัน'))

            used_by_others = self.env['vendor.payment.report'].search([
                ('state', '!=', 'cancel'),
                ('id', '!=', record.id),
                ('bill_ids', 'in', record.bill_ids.ids)
            ])
            if used_by_others:
                raise UserError(_('มีบิลบางรายการ ถูกผูกกับรายงานการชำระเงินใบอื่นไปแล้ว (%s)! กรุณาลบและเลือกใหม่')
                                % used_by_others.mapped('name'))

            record.is_confirmed = True
            record.is_cancelled = False

    def action_cancel(self):
        """ปุ่มกดยกเลิก"""
        for record in self:
            record.is_cancelled = True
            record.is_confirmed = False

    def action_draft(self):
        """ปุ่มกลับไปเป็นร่าง"""
        for record in self:
            record.is_confirmed = False
            record.is_cancelled = False
