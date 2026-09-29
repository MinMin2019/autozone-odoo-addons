# -*- coding: utf-8 -*-
"""ใบวางบิลบริษัทประกัน (รูปแบบที่ 3) + Export Excel  — v18.0.1.6.0
v18.0.1.7.0: ช่อง "เป็นบริษัทประกัน" บนลูกค้า + กรองลูกค้าเมื่อติ๊กใบวางบิลประกัน

ที่มาของข้อมูลแต่ละคอลัมน์ (ตรวจกับใบจริงของธนชาตประกันภัย 24 ก.ย. 2569):
    เลขที่เอกสาร   = เลขใบแจ้งหนี้            เลขเคลม      = x_claim_reference
    เลขที่เสนอราคา = x_job_reference          เลขกรมธรรม์  = x_policy_reference
    ยี่ห้อ          = x_brand_reference        ทะเบียนรถ    = x_car_reg_reference
    ค่าอะไหล่      = บรรทัดที่ลงบัญชีรายได้ขึ้นต้น 42 (รายได้จากการขาย เช่น 421001)
    ค่าแรง         = ยอดก่อน VAT ที่เหลือทั้งหมด (411000 ฯลฯ)
    Excess         = กรอกเองต่อใบแจ้งหนี้ (bn_excess_amount)
    VAT            = ผลรวม VAT จริงของใบแจ้งหนี้ (ไม่คิด 7% ใหม่ → ยอดตรงลูกหนี้ใน Odoo)
    หัก ณ ที่จ่าย   = ยอดก่อน VAT รวม x wht_percent (ค่าเริ่มต้น 3%)
    เงินที่ได้รับ    = ยอดรวม VAT - หัก ณ ที่จ่าย - Excess
(ฟิลด์ x_* มาจากโมดูล custom_invoice_print)
"""
import base64
import io
import re

from odoo import api, fields, models

PARTS_ACCOUNT_PREFIX = '42'   # รหัสบัญชีรายได้ที่นับเป็น "ค่าอะไหล่"

THAI_MONTHS = ['', 'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
               'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']


class AccountMove(models.Model):
    _inherit = 'account.move'

    bn_excess_amount = fields.Monetary(
        string='Excess เก็บจากลูกค้า', copy=False, currency_field='currency_id',
        help='ค่าเสียหายส่วนแรกที่อู่เก็บจากลูกค้าเอง (กรอกเอง) '
             'ใบวางบิลประกันจะนำไปหักออกจากยอดที่บริษัทประกันต้องจ่าย')
    bn_parts_amount = fields.Monetary(
        string='ค่าอะไหล่', compute='_compute_bn_parts_labor', currency_field='currency_id')
    bn_labor_amount = fields.Monetary(
        string='ค่าแรง', compute='_compute_bn_parts_labor', currency_field='currency_id')

    @api.depends('invoice_line_ids.price_subtotal', 'invoice_line_ids.account_id', 'amount_untaxed')
    def _compute_bn_parts_labor(self):
        for move in self:
            parts = sum(
                line.price_subtotal
                for line in move.invoice_line_ids
                if line.display_type == 'product'
                and (line.account_id.code or '').startswith(PARTS_ACCOUNT_PREFIX)
            )
            move.bn_parts_amount = parts
            move.bn_labor_amount = (move.amount_untaxed or 0.0) - parts


class ResPartner(models.Model):
    _inherit = 'res.partner'

    az_is_insurer = fields.Boolean(
        string='เป็นบริษัทประกัน', tracking=True,
        help='ติ๊กเมื่อลูกค้ารายนี้เป็นบริษัทประกันภัย: ใบวางบิลที่ติ๊ก "ใบวางบิลประกัน" '
             'จะเลือกได้เฉพาะลูกค้าที่ติ๊กช่องนี้ (ลูกค้าประกันรายใหม่ต้องติ๊กเอง)')

    # คำในชื่อที่ถือว่าเป็นบริษัทประกัน / คำที่ต้องตัดออก (ใช้ตอนติ๊กตั้งต้นครั้งแรก)
    _AZ_INSURER_WORDS = ('ประกันภัย', 'อินชัวร์', 'insurance')
    _AZ_INSURER_EXCLUDE = ('ประกันสังคม',)

    @api.model
    def az_mark_insurers(self):
        """ติ๊ก 'เป็นบริษัทประกัน' ตั้งต้นจากชื่อ (เรียกครั้งเดียวจาก migration 18.0.1.7.0)
        คืนค่า recordset ที่ถูกติ๊กใหม่"""
        domain = [('is_company', '=', True), ('az_is_insurer', '=', False)]
        domain += ['|'] * (len(self._AZ_INSURER_WORDS) - 1)
        domain += [('name', 'ilike', w) for w in self._AZ_INSURER_WORDS]
        partners = self.with_context(active_test=False).search(domain)
        partners = partners.filtered(
            lambda p: not any(x in (p.name or '') for x in self._AZ_INSURER_EXCLUDE))
        partners.write({'az_is_insurer': True})
        return partners


class CustomerBillingNote(models.Model):
    _inherit = 'customer.billing.note'

    is_insurance = fields.Boolean(
        string='ใบวางบิลประกัน', compute='_compute_is_insurance', store=True, readonly=False,
        help='ติ๊กเมื่อลูกค้าเป็นบริษัทประกัน: แสดงคอลัมน์เลขเคลม/ค่าอะไหล่/ค่าแรง/Excess '
             'ยอดหัก ณ ที่จ่าย และปุ่ม Export Excel; ติ๊กแล้วช่องลูกค้าจะเหลือเฉพาะบริษัทประกัน '
             '(ระบบติ๊กให้เองเมื่อเลือกลูกค้าที่ตั้งค่า "เป็นบริษัทประกัน")')
    insurance_branch = fields.Char(string='สาขา (บริษัทประกัน)')
    wht_percent = fields.Float(string='หัก ณ ที่จ่าย (%)', default=3.0, digits=(5, 2))

    ins_amount_untaxed = fields.Monetary(string='รวมก่อน VAT', compute='_compute_ins_amounts')
    ins_amount_tax = fields.Monetary(string='ภาษีมูลค่าเพิ่ม', compute='_compute_ins_amounts')
    ins_amount_total = fields.Monetary(string='จำนวนเงินรวม VAT', compute='_compute_ins_amounts')
    ins_amount_wht = fields.Monetary(string='หักภาษี ณ ที่จ่าย', compute='_compute_ins_amounts')
    ins_amount_excess = fields.Monetary(string='Excess', compute='_compute_ins_amounts')
    ins_amount_net = fields.Monetary(string='จำนวนเงินที่ได้รับ', compute='_compute_ins_amounts')

    @api.depends('partner_id')
    def _compute_is_insurance(self):
        """เลือกลูกค้าแล้ว → ตามค่า 'เป็นบริษัทประกัน' ของลูกค้า
        ยังไม่เลือกลูกค้า → คงค่าที่ผู้ใช้ติ๊กไว้ (ติ๊กก่อนเพื่อกรองรายชื่อลูกค้า)"""
        for rec in self:
            if rec.partner_id:
                rec.is_insurance = rec.partner_id.az_is_insurer
            else:
                rec.is_insurance = rec.is_insurance

    @api.depends('invoice_ids', 'invoice_ids.amount_untaxed', 'invoice_ids.amount_tax',
                 'invoice_ids.amount_total', 'invoice_ids.bn_excess_amount', 'wht_percent')
    def _compute_ins_amounts(self):
        for rec in self:
            cur = rec.currency_id or rec.company_id.currency_id
            untaxed = sum(rec.invoice_ids.mapped('amount_untaxed'))
            tax = sum(rec.invoice_ids.mapped('amount_tax'))
            excess = sum(rec.invoice_ids.mapped('bn_excess_amount'))
            wht = untaxed * (rec.wht_percent or 0.0) / 100.0
            wht = cur.round(wht) if cur else round(wht, 2)
            rec.ins_amount_untaxed = untaxed
            rec.ins_amount_tax = tax
            rec.ins_amount_total = untaxed + tax
            rec.ins_amount_wht = wht
            rec.ins_amount_excess = excess
            rec.ins_amount_net = untaxed + tax - wht - excess

    # ------------------------------------------------------------------
    # ข้อมูลกลาง ใช้ทั้ง PDF และ Excel
    # ------------------------------------------------------------------
    def ins_thai_date(self):
        self.ensure_one()
        d = self.date
        if not d:
            return ''
        return '%d %s %d' % (d.day, THAI_MONTHS[d.month], d.year + 543)

    def ins_rows(self):
        """1 ใบแจ้งหนี้ = 1 แถว (เลขเคลมซ้ำก็แยกแถว) เรียงตามเลขที่เอกสาร"""
        self.ensure_one()
        rows = []
        for seq, inv in enumerate(self.invoice_ids.sorted(key=lambda m: (m.name or '', m.id)), 1):
            rows.append({
                'seq': seq,
                'name': inv.name or '',
                'claim': inv.x_claim_reference or '',
                'job': inv.x_job_reference or '',
                'policy': inv.x_policy_reference or '',
                'brand': inv.x_brand_reference or '',
                'car_reg': inv.x_car_reg_reference or '',
                'parts': inv.bn_parts_amount,
                'labor': inv.bn_labor_amount,
                'total': inv.amount_untaxed,
                'excess': inv.bn_excess_amount or 0.0,
            })
        return rows

    def ins_tax_label(self):
        """ป้าย VAT เช่น 'จำนวนภาษีมูลค่าเพิ่ม 7%' (คำนวณ % จากยอดจริง กันกรณีอัตราเปลี่ยน)"""
        self.ensure_one()
        if self.ins_amount_untaxed:
            pct = round(self.ins_amount_tax / self.ins_amount_untaxed * 100)
            return 'จำนวนภาษีมูลค่าเพิ่ม %d%%' % pct
        return 'จำนวนภาษีมูลค่าเพิ่ม'

    def ins_wht_label(self):
        self.ensure_one()
        return 'หักภาษี %s%%' % ('%g' % (self.wht_percent or 0.0))

    # ------------------------------------------------------------------
    # Export Excel
    # ------------------------------------------------------------------
    def action_export_insurance_xlsx(self):
        self.ensure_one()
        data = self._build_insurance_xlsx()
        safe_name = re.sub(r'[^\w\-.]+', '_', self.name or 'billing_note')
        attachment = self.env['ir.attachment'].create({
            'name': '%s_insurance.xlsx' % safe_name,
            'type': 'binary',
            'datas': base64.b64encode(data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'self',
        }

    def _build_insurance_xlsx(self):
        import xlsxwriter

        self.ensure_one()
        company = self.company_id
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        ws = wb.add_worksheet('ใบวางบิล')

        font = {'font_name': 'Tahoma', 'font_size': 10}
        f_txt = wb.add_format(dict(font))
        f_bold = wb.add_format(dict(font, bold=True))
        f_title = wb.add_format(dict(font, bold=True, font_size=12, align='center'))
        f_center = wb.add_format(dict(font, align='center'))
        f_head = wb.add_format(dict(font, bold=True, align='center', valign='vcenter',
                                    top=1, bottom=1, text_wrap=True))
        f_head_ex = wb.add_format(dict(font, bold=True, align='center', valign='vcenter',
                                       top=1, bottom=1, text_wrap=True, bg_color='#F8CBAD'))
        f_cell = wb.add_format(dict(font))
        f_cell_c = wb.add_format(dict(font, align='center'))
        f_num = wb.add_format(dict(font, num_format='#,##0.00;-#,##0.00;"-"'))
        f_num0 = wb.add_format(dict(font, num_format='#,##0.00'))
        f_sum_lbl = wb.add_format(dict(font, bold=True, align='right', top=1))
        f_sum_num = wb.add_format(dict(font, bold=True, num_format='#,##0.00', top=1))
        f_sum_blank = wb.add_format(dict(font, top=1))
        f_tot_lbl = wb.add_format(dict(font, align='left'))
        f_tot_num = wb.add_format(dict(font, num_format='#,##0.00'))
        f_net_lbl = wb.add_format(dict(font, bold=True, align='left', top=1, bottom=6))
        f_net_num = wb.add_format(dict(font, bold=True, num_format='#,##0.00', top=1, bottom=6))

        # ความกว้างคอลัมน์ A..K
        for col, width in enumerate([7, 16, 21, 15, 21, 13, 16, 13, 13, 13, 13]):
            ws.set_column(col, col, width)

        # ---------------- หัวกระดาษ ----------------
        if company.logo:
            try:
                ws.insert_image(0, 0, 'logo.png', {
                    'image_data': io.BytesIO(base64.b64decode(company.logo)),
                    'x_scale': 0.45, 'y_scale': 0.45, 'x_offset': 4, 'y_offset': 2,
                    'object_position': 1,
                })
            except Exception:  # โลโก้เสีย/ฟอร์แมตแปลก ไม่ควรทำให้ export ล้ม
                pass
        ws.set_row(0, 22)
        ws.write(0, 3, company.name or '', f_bold)
        ws.write(1, 3, company.partner_id.get_thai_address() or '', f_txt)
        ws.write(2, 3, 'เลขประจำตัวผู้เสียภาษีอากร %s' % (company.vat or ''), f_txt)
        ws.merge_range(3, 0, 3, 10, 'ใบวางบิล-รายการตั้งเบิก', f_title)
        ws.merge_range(4, 0, 4, 10, 'วันที่ : %s' % self.ins_thai_date(), f_center)
        ws.write(5, 8, 'เลขที่ใบวางบิล: %s' % (self.name or ''), f_txt)
        ws.write(6, 0, 'บริษัทประกันภัย: %s' % (self.partner_id.name or ''), f_txt)
        ws.write(6, 6, 'สาขา: %s' % (self.insurance_branch or ''), f_txt)

        # ---------------- หัวตาราง (2 แถว) ----------------
        r = 8
        ws.set_row(r, 20)
        ws.set_row(r + 1, 20)
        for col, label in [(0, 'ลำดับ'), (1, 'เลขที่เอกสาร'), (2, 'เลขเคลม'),
                           (3, 'เลขที่เสนอราคา'), (4, 'เลขที่กรมธรรม์'), (9, 'รวม')]:
            ws.merge_range(r, col, r + 1, col, label, f_head)
        ws.merge_range(r, 5, r, 6, 'รายละเอียดรถ', f_head)
        ws.write(r + 1, 5, 'ยี่ห้อ', f_head)
        ws.write(r + 1, 6, 'ทะเบียนรถ', f_head)
        ws.write(r, 7, 'ค่าอะไหล่', f_head)
        ws.write(r + 1, 7, 'อนุมัติ', f_head)
        ws.write(r, 8, 'ค่าแรง', f_head)
        ws.write(r + 1, 8, 'อนุมัติ', f_head)
        ws.write(r, 10, 'Excess เก็บ', f_head_ex)
        ws.write(r + 1, 10, 'จากลูกค้า', f_head_ex)
        ws.freeze_panes(r + 2, 0)

        # ---------------- รายการ ----------------
        r += 2
        first_data = r
        rows = self.ins_rows()
        for row in rows:
            ws.write_number(r, 0, row['seq'], f_cell_c)
            ws.write_string(r, 1, row['name'], f_cell)
            ws.write_string(r, 2, row['claim'], f_cell)
            ws.write_string(r, 3, row['job'], f_cell_c)
            ws.write_string(r, 4, row['policy'], f_cell_c)
            ws.write_string(r, 5, row['brand'], f_cell_c)
            ws.write_string(r, 6, row['car_reg'], f_cell_c)
            ws.write_number(r, 7, row['parts'], f_num)
            ws.write_number(r, 8, row['labor'], f_num0)
            ws.write_number(r, 9, row['total'], f_num0)
            ws.write_number(r, 10, row['excess'], f_num0)
            r += 1
        last_data = r - 1

        # ---------------- ยอดรวม ----------------
        r += 1
        for col in range(0, 7):
            ws.write_blank(r, col, None, f_sum_blank)
        ws.write(r, 8, 'รวม', f_sum_lbl)
        ws.write_blank(r, 7, None, f_sum_blank)
        if rows:
            ws.write_formula(r, 9, '=SUM(J%d:J%d)' % (first_data + 1, last_data + 1),
                             f_sum_num, self.ins_amount_untaxed)
            ws.write_formula(r, 10, '=SUM(K%d:K%d)' % (first_data + 1, last_data + 1),
                             f_sum_num, self.ins_amount_excess)
        else:
            ws.write_number(r, 9, 0, f_sum_num)
            ws.write_number(r, 10, 0, f_sum_num)

        totals = [
            (self.ins_tax_label(), self.ins_amount_tax),
            ('จำนวนเงินรวม VAT', self.ins_amount_total),
            (self.ins_wht_label(), self.ins_amount_wht),
            ('Excess:', self.ins_amount_excess),
        ]
        r += 1
        for label, value in totals:
            ws.merge_range(r, 7, r, 8, label, f_tot_lbl)
            ws.write_number(r, 9, value, f_tot_num)
            r += 1
        ws.merge_range(r, 7, r, 8, 'จำนวนเงินที่ได้รับ', f_net_lbl)
        ws.write_number(r, 9, self.ins_amount_net, f_net_num)

        # ---------------- ลายเซ็น ----------------
        r += 4
        ws.write(r, 1, 'ผู้รับวางบิล ______________________', f_txt)
        ws.write(r, 6, 'ผู้วางบิล ______________________', f_txt)
        ws.write(r + 1, 1, 'วันที่ _______/_______/_______', f_txt)
        ws.write(r + 1, 6, 'วันที่ _______/_______/_______', f_txt)

        # ---------------- ตั้งค่าหน้ากระดาษ ----------------
        ws.set_paper(9)          # A4
        ws.set_portrait()
        ws.fit_to_pages(1, 0)    # กว้างพอดี 1 หน้า ยาวกี่หน้าก็ได้
        ws.set_margins(left=0.4, right=0.4, top=0.5, bottom=0.5)
        ws.repeat_rows(8, 9)     # พิมพ์หัวตารางซ้ำทุกหน้า

        wb.close()
        return buf.getvalue()
