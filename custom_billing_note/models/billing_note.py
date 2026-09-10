from odoo import models, fields, api, _
from odoo.exceptions import UserError

class CustomerBillingNote(models.Model):
    _name = 'customer.billing.note'
    _description = 'Customer Billing Note (ใบวางบิล)'
    _inherit = ['mail.thread', 'mail.activity.mixin'] 
    _order = 'date desc, id desc'
    
    # 1. ส่วนหัวของเอกสาร (Header)
    name = fields.Char(string='เลขที่ใบวางบิล', required=True, copy=False, readonly=True, 
                       default=lambda self: _('New'))
    
    partner_id = fields.Many2one('res.partner', string='ลูกค้า', required=True, 
                                 domain=[('is_company', '=', True)])
    
    date = fields.Date(string='วันที่วางบิล', default=fields.Date.context_today, required=True)
    # due_date = fields.Date(string='วันครบกำหนดชำระ', tracking=True)

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    # =========================================================================
    # 2. ฟิลด์ Compute สำหรับกรอง Invoice (หัวใจสำคัญของการป้องกันการเลือกซ้ำ)
    # =========================================================================
    available_invoice_ids = fields.Many2many(
        'account.move',
        compute='_compute_available_invoices'
    )

    @api.depends('partner_id')
    def _compute_available_invoices(self):
        """คำนวณและกรองว่ามีใบแจ้งหนี้ใบไหนบ้างของลูกค้ารายนี้ที่ 'ยังว่างอยู่' และไม่โดนดึงไปวางบิลอื่นแล้ว"""
        for record in self:
            if not record.partner_id:
                record.available_invoice_ids = False
                continue

            # ค้นหาใบวางบิลทั้งหมดของลูกค้ารายนี้ที่ "ไม่ได้ถูกยกเลิก"
            domain_existing_notes = [
                ('partner_id', '=', record.partner_id.id),
                ('state', '!=', 'cancel'),
            ]
            if isinstance(record.id, int):
                domain_existing_notes.append(('id', '!=', record.id))

            existing_notes = self.env['customer.billing.note'].search(domain_existing_notes)
            used_invoice_ids = existing_notes.mapped('invoice_ids').ids

            domain_invoices = [
                ('partner_id', '=', record.partner_id.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['not_paid', 'partial']),
            ]
            
            if used_invoice_ids:
                domain_invoices.append(('id', 'not in', used_invoice_ids))
                
            record.available_invoice_ids = self.env['account.move'].search(domain_invoices)

    # =========================================================================
    # 3. ความสัมพันธ์กับใบแจ้งหนี้ (Many2many ตัวจริงที่จะแสดงหน้าจอ)
    # =========================================================================
    invoice_ids = fields.Many2many(
        'account.move',          
        'billing_note_move_rel', 
        'billing_id',            
        'move_id',               
        string='รายการใบแจ้งหนี้',
    )

    # 4. ยอดรวมและการคำนวณ (Computed Fields)
    amount_total = fields.Monetary(string='ยอดรวมวางบิล', compute='_compute_amount_total', store=True)

    # =========================================================================
    # 5. สถานะเอกสาร (State) - เปลี่ยนเป็นระบบอัตโนมัติ
    # =========================================================================
    # เพิ่มฟิลด์ไว้จำว่า User เคยกดปุ่ม Confirm หรือ Cancel หรือยัง
    is_confirmed = fields.Boolean(string='Is Confirmed', default=False, copy=False)
    is_cancelled = fields.Boolean(string='Is Cancelled', default=False, copy=False)

    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('confirmed', 'ยืนยัน'),
        ('done', 'ชำระแล้ว'),
        ('cancel', 'ยกเลิก')
    ], string='สถานะ', compute='_compute_state', store=True, tracking=True, default='draft')

    @api.depends('is_confirmed', 'is_cancelled', 'invoice_ids.payment_state')
    def _compute_state(self):
        """คำนวณสถานะอัตโนมัติ โดยอิงจากการกดปุ่มและสถานะการจ่ายเงินของ Invoices"""
        for record in self:
            if record.is_cancelled:
                record.state = 'cancel'
            elif not record.is_confirmed:
                record.state = 'draft'
            else:
                # ถ้ากดยืนยันแล้ว (is_confirmed = True) ให้เช็คสถานะการจ่ายเงินของ Invoices 
                if record.invoice_ids:
                    # เช็คว่า Invoice ทุกใบ จ่ายแล้ว (paid), อยู่ระหว่างโอน (in_payment) หรือยกเลิกหนี้ (reversed) หรือยัง
                    all_paid = all(inv.payment_state in ['paid', 'in_payment', 'reversed'] for inv in record.invoice_ids)
                    if all_paid:
                        record.state = 'done'
                    else:
                        record.state = 'confirmed'
                else:
                    record.state = 'confirmed'

    # ==========================
    # Logic & Methods (ฟังก์ชัน)
    # ==========================
    @api.depends('invoice_ids', 'invoice_ids.amount_total')
    def _compute_amount_total(self):
        """คำนวณยอดรวมจากยอดคงเหลือ (amount_residual) ของใบแจ้งหนี้ทุกใบที่เลือก"""
        for record in self:
            record.amount_total = sum(record.invoice_ids.mapped('amount_total'))

    @api.model_create_multi
    def create(self, vals_list):
        """เจนเลขที่เอกสารตอนกด Save"""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('customer.billing.note') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        """ปุ่มกดยืนยันใบวางบิล"""
        for record in self:
            if not record.invoice_ids:
                raise UserError(_('กรุณาเลือกใบแจ้งหนี้อย่างน้อย 1 ใบ ก่อนกดยืนยัน'))
            
            used_by_others = self.env['customer.billing.note'].search([
                ('state', '!=', 'cancel'),
                ('id', '!=', record.id),
                ('invoice_ids', 'in', record.invoice_ids.ids)
            ])
            if used_by_others:
                raise UserError(_('มีใบแจ้งหนี้บางรายการ ถูกผูกกับใบวางบิลอื่นไปแล้ว (%s)! กรุณาลบและเลือกใหม่') % used_by_others.mapped('name'))

            # เปลี่ยนจากการเซ็ต state ตรงๆ เป็นการเปิดใช้งานธง (Flag) แทน
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
