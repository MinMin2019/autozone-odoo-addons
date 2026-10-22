# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# ฟิลด์ Studio มีเฉพาะ DB ที่เคยใช้ Studio → เช็คก่อนใช้เสมอ (เหมือนรายงานตรวจเช็ค)
LOCATION_FIELD = 'x_studio_location'

CONDITIONS = [
    ('good', 'สภาพดี'),
    ('damaged', 'ชำรุด'),
    ('missing', 'ไม่พบ'),
]


class AssetHandover(models.Model):
    """ใบส่งมอบ / ส่งคืนทรัพย์สิน (ตามแบบฟอร์ม Autozone-ใบส่งมอบทรัพย์สินให้หน่วยงาน)

    1 ใบ = ผู้ส่ง 1 คน → ผู้รับ 1 คน; พิมพ์ไปเซ็นกระดาษ แล้วฝ่ายบัญชีกดยืนยันเมื่อได้ใบเซ็นคืน
    ยืนยันแล้วเปลี่ยนผู้ถือครอง/ที่ตั้ง และ (ถ้าเลือก) Analytic ของค่าเสื่อมงวดที่ยังไม่ลงบัญชี
    """
    _name = 'az.asset.handover'
    _description = 'Asset Handover'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Number', readonly=True, copy=False, default='/', tracking=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today, tracking=True)
    handover_type = fields.Selection(
        [('deliver', 'ส่งมอบ'), ('return', 'ส่งคืน')],
        string='Type', required=True, default='deliver', tracking=True,
        help='ส่งมอบ: มอบให้พนักงาน/หน่วยงาน หรือโอนย้ายระหว่างฝ่าย/สาขา\n'
             'ส่งคืน: คืนจากผู้ถือครอง เช่น ลาออก ย้ายงาน เลิกใช้ เปลี่ยนเครื่องใหม่ '
             '(ผู้รับคืน = ผู้จัดการต้นสังกัด เป็นผู้ถือครองคนใหม่)',
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('done', 'Done'), ('cancel', 'Cancelled')],
        string='Status', default='draft', required=True, readonly=True, copy=False, tracking=True,
    )
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)

    sender_id = fields.Many2one(
        'hr.employee', string='Sender', tracking=True, context={'active_test': False},
        help='ผู้ส่งมอบ = ผู้ถือครองปัจจุบัน (ว่างได้ ถ้าเป็นของใหม่ที่ยังไม่มีผู้ถือ)',
    )
    receiver_id = fields.Many2one(
        'hr.employee', string='Receiver', required=True, tracking=True,
        help='ผู้รับมอบ / ผู้รับคืน — จะเป็นผู้ถือครองคนใหม่เมื่อยืนยัน',
    )
    receiver_job = fields.Char(string='Position', compute='_compute_receiver_info')
    receiver_code = fields.Char(string='Employee Code', compute='_compute_receiver_info')
    receiver_department_id = fields.Many2one(
        'hr.department', string='Department / Branch', compute='_compute_receiver_info')
    approver_id = fields.Many2one(
        'hr.employee', string='Approving Manager', tracking=True,
        help='ผู้จัดการต้นสังกัดของหน่วยงานปลายทาง (กรณีส่งคืน = หน่วยงานที่รับคืน)\n'
             'ต้องไม่ใช่ผู้ส่งหรือผู้รับ',
    )
    reason = fields.Text(string='Reason / Details')
    location_dest = fields.Char(
        string='New Location', help='ที่ตั้งใหม่ — ว่าง = ไม่เปลี่ยน Location ของทรัพย์สิน')

    # ส่วนที่ 4 ของแบบฟอร์ม
    receiver_check = fields.Selection(
        [('match', 'ตรง'), ('mismatch', 'ไม่ตรง')], string='Receiver Check',
        help='ผู้รับตรวจสอบแล้ว ครบถ้วน สภาพตรงตามรายการ')
    mismatch_note = fields.Char(string='Mismatch Details')
    hr_notified = fields.Boolean(string='HR Notified', help='ส่งคืนเพราะลาออก/ย้ายงาน — แจ้งฝ่ายบุคคลแล้ว')
    supervisor_notified = fields.Boolean(
        string='Supervisor Notified', help='ส่งคืนไม่ครบ/ชำรุด — แจ้งผู้บังคับบัญชาแล้ว')

    # กล่องฝ่ายบัญชี: ศูนย์ต้นทุนของค่าเสื่อม บัญชีเลือกเองทุกครั้ง (ไม่เดาจากแผนก)
    update_analytic = fields.Boolean(
        string='Change Depreciation Analytic',
        help='ติ๊ก = เปลี่ยน Analytic ของทรัพย์สินทุกรายการเป็นค่าด้านล่างเมื่อยืนยัน\n'
             'มีผลกับรายการค่าเสื่อมที่ยังเป็น Draft เท่านั้น (ที่ Post แล้วไม่เปลี่ยน)\n'
             'ไม่ติ๊ก = ไม่ต้องปรับ',
    )
    analytic_distribution = fields.Json(string='New Analytic')
    analytic_precision = fields.Integer(
        default=lambda self: self.env['decimal.precision'].precision_get('Percentage Analytic'))
    done_user_id = fields.Many2one('res.users', string='Recorded By', readonly=True, copy=False)
    done_date = fields.Datetime(string='Recorded On', readonly=True, copy=False)

    line_ids = fields.One2many('az.asset.handover.line', 'handover_id', string='Assets', copy=True)
    line_count = fields.Integer(compute='_compute_line_count')

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'เลขที่ใบส่งมอบซ้ำ'),
    ]

    @api.depends('receiver_id')
    def _compute_receiver_info(self):
        # user บัญชีไม่มีสิทธิ์ HR → ตำแหน่ง/แผนกอ่านจาก hr.employee.public, รหัสพนักงานติดกลุ่ม HR อ่านแบบ sudo
        for rec in self:
            pub = self.env['hr.employee.public'].browse(rec.receiver_id.id) if rec.receiver_id else None
            rec.receiver_job = pub and (pub.job_title or pub.job_id.name) or False
            rec.receiver_department_id = pub and pub.department_id or False
            rec.receiver_code = rec.receiver_id.sudo().registration_number or False

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    # ---------- ค่าเริ่มต้น ----------
    def _department_manager(self, employee, exclude):
        """ผู้จัดการของแผนกพนักงาน ไล่ขึ้นตามผังจนเจอคนที่ไม่อยู่ใน exclude (หลายแผนกยังไม่มีผู้จัดการ)"""
        dept = self.env['hr.employee.public'].browse(employee.id).department_id if employee else False
        while dept:
            manager = dept.sudo().manager_id
            if manager and manager not in exclude:
                return manager
            dept = dept.parent_id
        return self.env['hr.employee']

    @api.onchange('handover_type', 'sender_id')
    def _onchange_return_receiver(self):
        # ส่งคืน → ผู้รับคืนเริ่มต้น = ผู้จัดการต้นสังกัดของผู้ส่ง (แก้ได้)
        if self.handover_type == 'return' and self.sender_id and not self.receiver_id:
            self.receiver_id = self._department_manager(self.sender_id, self.sender_id)

    @api.onchange('receiver_id', 'sender_id')
    def _onchange_approver(self):
        if self.receiver_id:
            exclude = self.receiver_id | self.sender_id
            if not self.approver_id or self.approver_id in exclude:
                self.approver_id = self._department_manager(self.receiver_id, exclude)

    # ---------- เลขที่เอกสาร AST + ปี 2 หลัก + เดือน + ลำดับ 4 หลัก รีเซ็ตทุกเดือน ----------
    @api.model
    def _next_number(self, doc_date):
        # ใช้เดือนของวันที่เอกสาร (ไม่ใช่วันที่กดสร้าง)
        seq = self.env.ref('custom_asset_tracking.seq_asset_handover').sudo()
        first = doc_date.replace(day=1)
        last = first + relativedelta(months=1, days=-1)
        # Odoo สร้าง date range รายปีให้เอง → สร้างรายเดือนไว้ก่อน เลขจะรีเซ็ตทุกเดือน
        if not seq.date_range_ids.filtered(lambda r: r.date_from <= doc_date <= r.date_to):
            self.env['ir.sequence.date_range'].sudo().create({
                'sequence_id': seq.id, 'date_from': first, 'date_to': last, 'number_next': 1})
        return seq.with_context(ir_sequence_date=doc_date).next_by_id()

    @api.model_create_multi
    def create(self, vals_list):
        # ออกเลขก่อน INSERT ตั้งแต่สร้าง — ใบที่พิมพ์ไปเซ็นต้องมีเลขที่แล้ว (ใบที่ยกเลิกเลขก็ข้ามไป)
        # (ตั้งหลัง create ไม่ได้: UPDATE ยังไม่ flush แล้ว INSERT ใบถัดไปชน unique "/")
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                doc_date = fields.Date.to_date(vals.get('date')) or fields.Date.context_today(self)
                vals['name'] = self._next_number(doc_date)
        records = super().create(vals_list)
        # สร้างจากโค้ด/นำเข้า (ไม่ผ่าน onchange) → เติมผู้จัดการต้นสังกัดให้เหมือนกรอกบนหน้าจอ
        for rec in records.filtered(lambda r: not r.approver_id and r.receiver_id):
            rec.approver_id = rec._department_manager(rec.receiver_id, rec.receiver_id | rec.sender_id)
        return records

    # ---------- ปุ่ม ----------
    def action_done(self):
        for rec in self:
            rec._check_before_done()
        for rec in self:
            rec._apply_to_assets()
            rec.write({'state': 'done', 'done_user_id': self.env.uid, 'done_date': fields.Datetime.now()})
        return True

    def action_cancel(self):
        if self.filtered(lambda r: r.state == 'done'):
            raise UserError(_('ใบที่ยืนยันแล้วยกเลิกไม่ได้ — ถ้าส่งผิด ให้ทำใบส่งมอบกลับ'))
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.filtered(lambda r: r.state == 'cancel').write({'state': 'draft'})

    def action_print(self):
        return self.env.ref('custom_asset_tracking.action_report_asset_handover').report_action(self)

    def _check_before_done(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('ใบ %s ไม่ได้อยู่ในสถานะ Draft') % self.name)
        if not self.line_ids:
            raise UserError(_('กรุณาเพิ่มรายการทรัพย์สิน'))
        if self.update_analytic and not self.analytic_distribution:
            raise UserError(_('ติ๊กเปลี่ยน Analytic แล้ว กรุณาเลือก Analytic ใหม่'))
        errors = []
        for line in self.line_ids:
            asset = line.asset_id
            if asset.state not in ('draft', 'open', 'paused'):
                errors.append(_('%s: สถานะ %s ส่งมอบไม่ได้') % (asset.display_name, asset.state))
            elif asset.custodian_id and asset.custodian_id != self.sender_id:
                errors.append(_('%s: ผู้ถือครองปัจจุบันคือ %s ไม่ใช่ผู้ส่ง') % (
                    asset.display_name,
                    self.env['hr.employee.public'].browse(asset.custodian_id.id).name))
        if errors:
            raise UserError(_('ยืนยันไม่ได้:\n') + '\n'.join(errors))

    def _apply_to_assets(self):
        """เปลี่ยนผู้ถือครอง/ที่ตั้ง/Analytic + เก็บค่าเดิมไว้ที่บรรทัดเป็นประวัติ
        รายการ "ไม่พบ" ไม่เปลี่ยนอะไร (ของหาย ไม่ได้ส่งมอบจริง)"""
        self.ensure_one()
        has_location = LOCATION_FIELD in self.env['account.asset']._fields
        for line in self.line_ids:
            asset = line.asset_id
            line.write({
                'from_custodian_id': asset.custodian_id.id,
                'from_location': asset[LOCATION_FIELD] if has_location else False,
                'from_analytic_distribution': asset.analytic_distribution,
            })
            if line.condition == 'missing':
                asset.message_post(body=_('ใบส่งมอบ %s: ไม่พบทรัพย์สิน — ไม่เปลี่ยนผู้ถือครอง') % self.name)
                continue
            vals = {'custodian_id': self.receiver_id.id}
            if has_location and self.location_dest:
                vals[LOCATION_FIELD] = self.location_dest
            if self.update_analytic:
                # write ของ account.asset เปลี่ยน analytic ของรายการค่าเสื่อมที่ยัง Draft ให้เอง
                vals['analytic_distribution'] = self.analytic_distribution
            asset.write(vals)
            asset.message_post(body=_('ใบส่งมอบ %s (%s) ยืนยันแล้ว') % (
                self.name, dict(self._fields['handover_type'].selection)[self.handover_type]))

    @api.constrains('sender_id', 'receiver_id', 'approver_id')
    def _check_people(self):
        for rec in self:
            if rec.sender_id and rec.sender_id == rec.receiver_id:
                raise ValidationError(_('ผู้ส่งและผู้รับต้องเป็นคนละคน'))
            if rec.approver_id and rec.approver_id in (rec.sender_id | rec.receiver_id):
                raise ValidationError(_('ผู้จัดการต้นสังกัด (ผู้อนุมัติ) ต้องไม่ใช่ผู้ส่งหรือผู้รับ'))

    def unlink(self):
        if self.filtered(lambda r: r.state == 'done'):
            raise UserError(_('ลบใบที่ยืนยันแล้วไม่ได้'))
        return super().unlink()

    # ---------- สร้างจากลิสต์ทรัพย์สิน ----------
    @api.model
    def action_new_from_assets(self, assets):
        custodians = assets.custodian_id
        ctx = {
            'default_line_ids': [(0, 0, {'asset_id': a.id}) for a in assets],
            'default_sender_id': custodians.id if len(custodians) == 1 else False,
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Asset Handover'),
            'res_model': 'az.asset.handover',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }


class AssetHandoverLine(models.Model):
    _name = 'az.asset.handover.line'
    _description = 'Asset Handover Line'
    _order = 'handover_id, sequence, id'

    handover_id = fields.Many2one('az.asset.handover', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    asset_id = fields.Many2one(
        'account.asset', string='Asset', required=True, index=True,
        domain="[('state', 'in', ('draft', 'open', 'paused'))]")
    condition = fields.Selection(CONDITIONS, string='Condition', default='good', required=True)
    note = fields.Char(string='Note')

    # ค่าเดิมตอนยืนยัน (ประวัติ)
    from_custodian_id = fields.Many2one('hr.employee', string='Previous Custodian', readonly=True)
    from_location = fields.Char(string='Previous Location', readonly=True)
    from_analytic_distribution = fields.Json(string='Previous Analytic', readonly=True)

    # ใช้แสดง/ค้นประวัติจากฝั่งทรัพย์สิน
    date = fields.Date(related='handover_id.date', store=True)
    state = fields.Selection(related='handover_id.state', store=True)
    handover_type = fields.Selection(related='handover_id.handover_type')
    receiver_id = fields.Many2one(related='handover_id.receiver_id')

    _sql_constraints = [
        ('asset_uniq', 'unique(handover_id, asset_id)', 'ทรัพย์สินซ้ำในใบเดียวกัน'),
    ]


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    handover_line_ids = fields.One2many('az.asset.handover.line', 'asset_id', string='Handovers')
    handover_count = fields.Integer(compute='_compute_handover_count')

    def _compute_handover_count(self):
        data = self.env['az.asset.handover.line']._read_group(
            [('asset_id', 'in', self.ids), ('state', '=', 'done')], ['asset_id'], ['__count'])
        counts = {asset.id: count for asset, count in data}
        for asset in self:
            asset.handover_count = counts.get(asset.id, 0)

    def action_view_handovers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Handover History'),
            'res_model': 'az.asset.handover.line',
            'view_mode': 'list',
            'views': [(self.env.ref('custom_asset_tracking.view_az_asset_handover_line_history').id, 'list')],
            'domain': [('asset_id', '=', self.id), ('state', '=', 'done')],
        }

    def action_create_handover(self):
        return self.env['az.asset.handover'].action_new_from_assets(self)


# แบ่งหน้าใบส่งมอบ (A4 แนวนอน ขอบ 8 มม. หน่วย px แบบเดียวกับรายงานตรวจเช็ค)
# ⚠️ แก้ความสูงใน template report/asset_handover_report.xml ต้องแก้ค่าคู่กันที่นี่
HO_PAGE_H = 860
HO_TOP_H = 250   # หัวเอกสาร + ส่วนที่ 1 + ส่วนที่ 2 (หน้าแรก)
HO_THEAD_H = 46  # หัวตาราง 2 ชั้น (ทุกหน้า)
HO_ROW_H = 54    # แถวทรัพย์สิน
HO_END_H = 330   # ส่วนที่ 4 + ลายเซ็น 3 ช่อง + กล่องฝ่ายบัญชี + ข้อกำหนด (หน้าสุดท้าย)


class AssetHandoverReport(models.AbstractModel):
    _name = 'report.custom_asset_tracking.report_asset_handover'
    _description = 'Asset Handover Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        handovers = self.env['az.asset.handover'].browse(docids)
        Asset = self.env['account.asset']
        has_code = 'x_studio_asset_code' in Asset._fields
        has_location = LOCATION_FIELD in Asset._fields
        Public = self.env['hr.employee.public'].with_context(active_test=False)
        docs = []
        for ho in handovers:
            rows = []
            for seq, line in enumerate(ho.line_ids, 1):
                asset = line.asset_id
                rows.append({
                    'seq': seq,
                    'line': line,
                    'asset': asset,
                    'code': (asset.x_studio_asset_code or '') if has_code else '',
                    # ยืนยันแล้ว Location เปลี่ยนเป็นที่ใหม่ → พิมพ์ที่เดิมตอนส่งมอบ
                    'location': (line.from_location if ho.state == 'done'
                                 else (asset[LOCATION_FIELD] if has_location else '')) or '',
                })
            docs.append({
                'ho': ho,
                'pages': self._paginate(rows),
                # ชื่อคนอ่านจาก hr.employee.public — user บัญชีส่วนใหญ่ไม่มีสิทธิ์ HR
                'sender': Public.browse(ho.sender_id.id).name or '',
                'receiver': Public.browse(ho.receiver_id.id).name or '',
                'approver': Public.browse(ho.approver_id.id).name or '',
            })
        return {
            'doc_ids': handovers.ids,
            'doc_model': 'az.asset.handover',
            'docs': docs,
        }

    @api.model
    def _paginate(self, rows):
        """หน้าสุดท้ายต้องมีที่ให้ส่วนที่ 4 + ลายเซ็น ไม่พอ → ยกรายการสุดท้ายไปหน้าใหม่ด้วย"""
        pages = [[]]
        used = HO_TOP_H + HO_THEAD_H
        for row in rows:
            if used + HO_ROW_H > HO_PAGE_H and pages[-1]:
                pages.append([])
                used = HO_THEAD_H
            pages[-1].append(row)
            used += HO_ROW_H
        if used + HO_END_H > HO_PAGE_H and len(pages[-1]) > 0 and len(rows) > 1:
            last = pages[-1].pop()
            if not pages[-1]:
                pages.pop()
            pages.append([last])
        return pages
