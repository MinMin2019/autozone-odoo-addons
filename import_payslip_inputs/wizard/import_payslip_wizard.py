# -*- coding: utf-8 -*-
import base64
import io
import json
import re

from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError

try:
    import openpyxl
except ImportError:
    openpyxl = None

# จำนวน error สูงสุดที่แสดงใน pop-up (กันข้อความยาวเกิน)
MAX_ERRORS_DISPLAY = 30

# รายการที่ห้ามมากับไฟล์ import เพราะมีโมดูลใน Odoo เป็นเจ้าของแล้ว (กันหักซ้ำ 2 ทาง)
# LOAN: custom_hr_loan push งวดหักเข้า Batch เองอัตโนมัติ (เคาะ 24 ส.ค. 2026)
BLOCKED_CODES = {
    'LOAN': 'รายการหักเงินกู้มาจากโมดูลเงินกู้สวัสดิการอัตโนมัติแล้ว ห้ามใส่ในไฟล์ (จะหักซ้ำ)',
}


def _cell_to_str(value):
    """แปลงค่าจาก cell ของ Excel เป็น string ที่สะอาด
    (กันเคสรหัสพนักงานเป็นตัวเลข เช่น 1001 ถูกอ่านมาเป็น float 1001.0)"""
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _norm_name(name):
    """เทียบชื่อแบบไม่สนช่องว่างซ้ำ/ตัวพิมพ์ (ชื่อจาก Business Plus มีช่องว่างเกินบ่อย)"""
    return re.sub(r'\s+', ' ', (name or '')).strip().casefold()


class ImportPayslipInputsWizard(models.TransientModel):
    _name = 'import.payslip.inputs.wizard'
    _description = 'Import Payslip Other Inputs Wizard'

    state = fields.Selection([
        ('upload', 'Upload'),
        ('preview', 'Preview'),
        ('result', 'Result'),
    ], default='upload', required=True)
    payslip_run_id = fields.Many2one(
        'hr.payslip.run', string='Payslip Batch', required=True, ondelete='cascade',
        default=lambda self: self.env.context.get('active_model') == 'hr.payslip.run'
                             and self.env.context.get('active_id') or False)
    currency_id = fields.Many2one(related='payslip_run_id.currency_id')
    file_data = fields.Binary(string='Excel File')
    file_name = fields.Char(string='File Name')
    line_ids = fields.One2many(
        'import.payslip.inputs.wizard.line', 'wizard_id', string='Preview Lines')

    # --- สรุปยอดสำหรับหน้า Preview (ใช้กระทบยอดกับระบบเก่า) ---
    line_count = fields.Integer(compute='_compute_summary')
    employee_count = fields.Integer(compute='_compute_summary')
    total_earning = fields.Monetary(compute='_compute_summary', currency_field='currency_id')
    total_deduction = fields.Monetary(compute='_compute_summary', currency_field='currency_id')
    total_company = fields.Monetary(compute='_compute_summary', currency_field='currency_id')
    skipped_note = fields.Char(readonly=True)
    # ชีต Control จากไฟล์ที่ bplus_extract.py สร้าง: {รหัสพนักงาน: {net, loan, earning, deduction}}
    control_json = fields.Text(readonly=True)
    control_note = fields.Char(readonly=True)
    warning_note = fields.Text(readonly=True)
    result_html = fields.Html(readonly=True, sanitize=False)

    @api.depends('line_ids.amount', 'line_ids.kind')
    def _compute_summary(self):
        for wizard in self:
            lines = wizard.line_ids
            wizard.line_count = len(lines)
            wizard.employee_count = len(lines.mapped('employee_id'))
            wizard.total_earning = sum(lines.filtered(lambda l: l.kind == 'earning').mapped('amount'))
            wizard.total_company = sum(lines.filtered(lambda l: l.kind == 'company').mapped('amount'))
            wizard.total_deduction = sum(lines.filtered(lambda l: l.kind == 'deduction').mapped('amount'))

    # ------------------------------------------------------------------
    # Template
    # ------------------------------------------------------------------
    def action_download_template(self):
        """สร้างไฟล์ Excel ต้นแบบ พร้อม sheet รายการรหัสที่ใช้ได้จริงจากระบบ"""
        if not openpyxl:
            raise UserError(_("Please install openpyxl library."))

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Import'
        ws.append(['รหัสพนักงาน (Registration Number)',
                   'ชื่อพนักงาน (ไว้ตรวจสอบ ปล่อยว่างได้)',
                   'รหัสรายการ (Input Code)',
                   'จำนวนเงิน (ใส่ค่าบวกเสมอ)'])
        ws.append(['1001', 'สมชาย ใจดี', 'BASIC', 25000])
        ws.append(['1001', 'สมชาย ใจดี', 'SSO', 750])
        for col, width in zip('ABCD', (32, 32, 24, 22)):
            ws.column_dimensions[col].width = width

        # Sheet 2: รายการ Input Code ที่ระบบรองรับ
        ws_codes = wb.create_sheet('Codes')
        ws_codes.append(['Input Code', 'คำอธิบาย'])
        structure = self.env.ref(
            'import_payslip_inputs.structure_legacy_import', raise_if_not_found=False)
        input_types = structure.input_line_type_ids if structure and structure.input_line_type_ids \
            else self.env['hr.payslip.input.type'].search([])
        for input_type in input_types.sorted('code'):
            ws_codes.append([input_type.code, input_type.name])
        ws_codes.column_dimensions['A'].width = 18
        ws_codes.column_dimensions['B'].width = 40

        fp = io.BytesIO()
        wb.save(fp)
        fp.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'Template_Payslip_Inputs.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(fp.read()),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    # ------------------------------------------------------------------
    # Step 1: Parse + Validate -> Preview
    # ------------------------------------------------------------------
    def action_parse_file(self):
        self.ensure_one()
        if not openpyxl:
            raise UserError(_("Please install openpyxl library in your Python environment."))
        if not self.file_data:
            raise UserError(_("กรุณาอัปโหลดไฟล์ Excel ก่อนกดตรวจสอบ"))

        batch = self.payslip_run_id
        if not batch:
            raise UserError(_("ไม่พบ Payslip Batch กรุณาเปิดหน้าต่างนี้จากหน้า Batch"))
        # batch ที่มีสลิปจะถูก core ปรับเป็น 'verify' (Confirmed) โดยอัตโนมัติ
        # (_compute_state_change) — สลิปยังแก้ได้อยู่ จึงต้องรับทั้ง draft/verify
        if batch.state not in ('draft', 'verify'):
            raise UserError(_("นำเข้าได้เฉพาะ Batch ที่ยังไม่ปิด (New/Confirmed) เท่านั้น"))

        try:
            file_content = base64.b64decode(self.file_data)
            wb = openpyxl.load_workbook(filename=io.BytesIO(file_content), data_only=True)
            sheet = wb['Import'] if 'Import' in wb.sheetnames else wb.active
        except Exception as e:
            raise UserError(_("ไฟล์ไม่ถูกต้อง กรุณาอัปโหลดไฟล์ .xlsx\nError: %s") % str(e))
        control = self._read_control_sheet(wb)

        emp_map, slip_map = self._prepare_employee_slip_maps(batch)
        type_map = self._prepare_input_type_map()
        kind_cache = {}

        errors = []
        name_warns = {}   # รหัสพนักงาน -> (ชื่อในไฟล์, ชื่อในระบบ) เฉพาะไฟล์ BPlus
        skipped_zero = 0
        # aggregated[(payslip_id, input_type_id)] = {'amount': .., 'rows': [..], 'employee': rec, 'type': rec}
        aggregated = {}

        for row_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            if row_idx == 1:
                continue
            row = tuple(row) + (None,) * (4 - len(row))
            emp_code = _cell_to_str(row[0])
            emp_name = _cell_to_str(row[1])
            input_code = _cell_to_str(row[2])
            raw_amount = row[3]

            if not emp_code and not emp_name and not input_code and raw_amount in (None, ''):
                continue  # แถวว่าง ข้ามได้

            if not emp_code:
                errors.append(_("บรรทัดที่ %s: ไม่ได้ระบุรหัสพนักงาน") % row_idx)
                continue
            if not input_code:
                errors.append(_("บรรทัดที่ %s: ไม่ได้ระบุรหัสรายการ (Input Code)") % row_idx)
                continue

            # 1) หาพนักงานจากรหัสพนักงานเท่านั้น (ไม่ใช้ชื่อ กันเงินเข้าผิดคน)
            employee = emp_map.get(emp_code.upper())
            if not employee:
                errors.append(_("บรรทัดที่ %s: ไม่พบพนักงานรหัส '%s' (ตรวจสอบ Registration Number ในระบบ)") % (row_idx, emp_code))
                continue

            # 2) ถ้าใส่ชื่อมาด้วย ให้ตรวจว่าตรงกับรหัส (กันกรอกรหัสผิดคน)
            if emp_name and _norm_name(emp_name) != _norm_name(employee.name):
                if control:
                    # ไฟล์จาก Business Plus: รหัสเป็นตัวชี้ขาด ชื่อสะกดต่างกันสองระบบเป็นเรื่องปกติ -> เตือนให้ HR ตามแก้
                    name_warns[emp_code] = (emp_name, employee.name)
                else:
                    errors.append(_("บรรทัดที่ %s: ชื่อ '%s' ไม่ตรงกับพนักงานรหัส '%s' (%s)") % (row_idx, emp_name, emp_code, employee.name))
                    continue

            # 3) ต้องมีสลิปใน Batch อยู่แล้ว (สร้างจาก Generate Payslips ก่อน)
            slips = slip_map.get(employee.id)
            if not slips:
                errors.append(_("บรรทัดที่ %s: พนักงาน '%s' ยังไม่มีสลิปใน Batch นี้ กรุณากด Generate Payslips ก่อน") % (row_idx, employee.name))
                continue
            if len(slips) > 1:
                errors.append(_("บรรทัดที่ %s: พนักงาน '%s' มีสลิปมากกว่า 1 ใบใน Batch ระบุอัตโนมัติไม่ได้") % (row_idx, employee.name))
                continue
            slip = slips[0]
            if slip.state not in ('draft', 'verify'):
                errors.append(_("บรรทัดที่ %s: สลิปของ '%s' อยู่ในสถานะ %s แก้ไขไม่ได้แล้ว") % (row_idx, employee.name, slip.state))
                continue

            # 4) หา Input Type จาก code เท่านั้น (ไม่เดาจากชื่อ)
            input_types = type_map.get(input_code.upper())
            if not input_types:
                errors.append(_("บรรทัดที่ %s: ไม่พบรหัสรายการ '%s' (ดูรหัสที่ใช้ได้ใน sheet 'Codes' ของ Template)") % (row_idx, input_code))
                continue
            if len(input_types) > 1:
                errors.append(_("บรรทัดที่ %s: รหัสรายการ '%s' ซ้ำกันหลายประเภทในระบบ กรุณาแก้ master data") % (row_idx, input_code))
                continue
            input_type = input_types[0]

            if input_type.code in BLOCKED_CODES:
                errors.append(_("บรรทัดที่ %s: %s") % (row_idx, BLOCKED_CODES[input_type.code]))
                continue

            # 5) ตรวจว่า Structure ของสลิปมี Salary Rule รองรับ input นี้ (กันเงินหายเงียบ ๆ)
            kind = self._get_input_kind(slip.struct_id, input_type, kind_cache)
            if kind is None:
                errors.append(_("บรรทัดที่ %s: รหัส '%s' ไม่มี Salary Rule รองรับใน Structure '%s' (ยอดจะไม่ถูกคำนวณ)") % (row_idx, input_code, slip.struct_id.name))
                continue

            # 6) ตรวจจำนวนเงิน (บวกเสมอ รายการหักระบบจะติดลบให้เองใน Rule)
            try:
                amount = float(str(raw_amount).replace(',', '').strip())
            except (ValueError, TypeError):
                errors.append(_("บรรทัดที่ %s: จำนวนเงิน '%s' ไม่ใช่ตัวเลขที่ถูกต้อง") % (row_idx, raw_amount))
                continue
            if amount < 0:
                errors.append(_("บรรทัดที่ %s: จำนวนเงินต้องเป็นค่าบวก (%s) รายการหักให้ใส่ค่าบวก ระบบจะหักให้เอง") % (row_idx, amount))
                continue
            if not amount:
                skipped_zero += 1
                continue

            # 7) code ซ้ำ (พนักงานเดิม + รหัสเดิม) -> รวมยอด และบันทึกไว้ให้เห็นใน Preview
            key = (slip.id, input_type.id)
            if key in aggregated:
                aggregated[key]['amount'] += amount
                aggregated[key]['rows'].append(row_idx)
            else:
                aggregated[key] = {
                    'slip': slip, 'employee': employee, 'type': input_type,
                    'kind': kind, 'amount': amount, 'rows': [row_idx],
                }

        # 8) ชีต Control (ไฟล์จาก Business Plus): รายได้ - รายการหัก ในไฟล์ ต้องเท่ากับ สุทธิ BPlus + เงินกู้
        #    (เงินกู้ไม่มาในไฟล์ โมดูลเงินกู้หักเอง) — กันไฟล์ที่ map รหัสผิดฝั่ง/ตกหล่นก่อนลง
        if control and not errors:
            per_emp = {}
            for data in aggregated.values():
                reg = (data['employee'].registration_number or '').strip().upper()
                t = per_emp.setdefault(reg, [0.0, 0.0])
                if data['kind'] == 'earning':
                    t[0] += data['amount']
                elif data['kind'] == 'deduction':
                    t[1] += data['amount']
            for reg, (earn, ded) in per_emp.items():
                c = control.get(reg)
                if not c:
                    continue
                expected = c['net'] + c['loan']
                if abs((earn - ded) - expected) > 0.005:
                    errors.append(_("Control: พนักงาน %s ยอดในไฟล์ (รายได้ %s - หัก %s = %s) ไม่เท่ากับ สุทธิ BPlus %s + เงินกู้ %s")
                                  % (reg, f"{earn:,.2f}", f"{ded:,.2f}", f"{earn - ded:,.2f}",
                                     f"{c['net']:,.2f}", f"{c['loan']:,.2f}"))
            missing_ctl = [reg for reg in per_emp if reg not in control]
            if missing_ctl:
                errors.append(_("Control: ไม่มียอดตรวจทานของพนักงาน %s") % ", ".join(missing_ctl[:20]))

        if errors:
            display = errors[:MAX_ERRORS_DISPLAY]
            if len(errors) > MAX_ERRORS_DISPLAY:
                display.append(_("...และข้อผิดพลาดอื่นอีก %s รายการ") % (len(errors) - MAX_ERRORS_DISPLAY))
            raise UserError(_("พบข้อผิดพลาด %s รายการ ยังไม่มีการนำเข้าใด ๆ กรุณาแก้ไฟล์แล้วลองใหม่:\n\n%s")
                            % (len(errors), "\n".join(display)))
        if not aggregated:
            raise UserError(_("ไม่พบข้อมูลที่นำเข้าได้ในไฟล์"))

        # สร้างบรรทัด Preview
        self.line_ids.unlink()
        line_vals = []
        for data in aggregated.values():
            note = ''
            if len(data['rows']) > 1:
                note = _("รวมยอดจาก %s แถว (บรรทัด %s)") % (len(data['rows']), ", ".join(map(str, data['rows'])))
            line_vals.append({
                'wizard_id': self.id,
                'payslip_id': data['slip'].id,
                'employee_id': data['employee'].id,
                'input_type_id': data['type'].id,
                'kind': data['kind'],
                'amount': data['amount'],
                'note': note,
            })
        self.env['import.payslip.inputs.wizard.line'].create(line_vals)
        self.skipped_note = skipped_zero and _("ข้าม %s แถวที่จำนวนเงินเป็น 0") % skipped_zero or False
        self.warning_note = name_warns and (
            _("ชื่อสะกดไม่ตรงกัน %s คน (นำเข้าตามรหัสพนักงาน — แจ้ง HR ตรวจการสะกดใน 2 ระบบ):\n") % len(name_warns)
            + "\n".join(f"{code}: ไฟล์ '{a}' / ระบบ '{b}'" for code, (a, b) in sorted(name_warns.items()))) or False
        self.control_json = json.dumps(control) if control else False
        self.control_note = control and _("มีชีต Control จาก Business Plus (%s คน) — ยอดในไฟล์ตรงกับสุทธิ BPlus ทุกคน "
                                          "หลังยืนยันระบบจะเทียบ NET ของสลิปให้อีกครั้ง") % len(control) or False
        self.state = 'preview'
        return self._reopen()

    # ------------------------------------------------------------------
    # Step 2: Confirm -> เขียนจริง (โหมด Replace ทั้งก้อน)
    # ------------------------------------------------------------------
    def action_confirm_import(self):
        self.ensure_one()
        if self.state != 'preview' or not self.line_ids:
            raise UserError(_("ไม่มีข้อมูลให้ยืนยัน กรุณาอัปโหลดและตรวจสอบไฟล์ก่อน"))

        batch = self.payslip_run_id
        slips = self.line_ids.mapped('payslip_id')

        # กันเคสสถานะเปลี่ยนไประหว่างที่ HR ดู Preview ค้างไว้
        locked = slips.filtered(lambda s: s.state not in ('draft', 'verify'))
        if locked:
            raise UserError(_("สลิปต่อไปนี้ถูกยืนยันไปแล้ว แก้ไขไม่ได้: %s")
                            % ", ".join(locked.mapped('employee_id.name')))

        # Replace ทั้งก้อน: ล้างเฉพาะ input ที่เคยมาจากการ import (ไม่แตะที่กรอกมือ)
        old_inputs = self.env['hr.payslip.input'].search([
            ('payslip_id', 'in', slips.ids),
            ('is_imported', '=', True),
        ])
        old_inputs.unlink()

        self.env['hr.payslip.input'].create([{
            'payslip_id': line.payslip_id.id,
            'input_type_id': line.input_type_id.id,
            'name': line.input_type_id.name,
            'amount': line.amount,
            'is_imported': True,
        } for line in self.line_ids])

        # คำนวณสลิปใหม่ทันที ให้ HR เห็นยอดถูกต้องโดยไม่ต้องกด Compute เอง
        slips.compute_sheet()

        # Audit trail: บันทึกลง chatter ของ Batch พร้อมแนบไฟล์ต้นฉบับ
        body = Markup(
            "<b>นำเข้ารายได้/รายการหักจาก Excel</b><ul>"
            "<li>ไฟล์: %s</li>"
            "<li>พนักงาน: %s คน / %s รายการ</li>"
            "<li>รวมรายได้: %s</li>"
            "<li>รวมรายการหัก: %s</li>"
            "<li>โหมด: ล้างรายการที่เคย import แล้วลงใหม่ทั้งชุดตามไฟล์</li></ul>"
        ) % (
            escape(self.file_name or '-'),
            self.employee_count, self.line_count,
            f"{self.total_earning:,.2f}", f"{self.total_deduction:,.2f}",
        )
        if self.warning_note:
            body += Markup("<p><b>คำเตือน</b></p><pre>%s</pre>") % self.warning_note
        attachments = []
        if self.file_data:
            attachments = [(self.file_name or 'import.xlsx', base64.b64decode(self.file_data))]
        batch.message_post(body=body, attachments=attachments)

        # เทียบ NET ของสลิปกับสุทธิ Business Plus (ถ้าไฟล์มีชีต Control)
        if self.control_json:
            result_body = self._compare_net_with_control(slips)
            batch.message_post(body=result_body)
            self.result_html = result_body
            self.state = 'result'
            return self._reopen()

        # reload หน้า Batch เพื่อให้ยอดที่คำนวณใหม่แสดงทันที
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_close_reload(self):
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _compare_net_with_control(self, slips):
        """สลิปแต่ละใบ: NET (Odoo) เทียบ สุทธิ BPlus — ต่างเท่ากับเงินกู้พอดี = แค่ยังไม่กดปุ่มหักเงินกู้พนักงาน"""
        control = json.loads(self.control_json or '{}')
        ok, wait_loan, bad = [], [], []
        for slip in slips:
            reg = (slip.employee_id.registration_number or '').strip().upper()
            c = control.get(reg)
            if not c:
                continue
            diff = slip.net_wage - c['net']
            if abs(diff) < 0.005:
                ok.append(slip)
            elif c['loan'] and abs(diff - c['loan']) < 0.005:
                wait_loan.append((slip, c))
            else:
                bad.append((slip, c, diff))
        head = Markup("<b>ผลเทียบ NET กับ Business Plus</b><ul><li>ตรง: %s คน</li>"
                      "<li>ต่างเท่ากับเงินกู้ (รอกด \"หักเงินกู้พนักงาน\"): %s คน</li>"
                      "<li>ไม่ตรง: %s คน</li></ul>") % (len(ok), len(wait_loan), len(bad))
        rows = Markup('')
        if bad:
            rows += Markup("<p><b>ไม่ตรง — ต้องตรวจก่อนปิดงวด</b></p><table class='table table-sm'><tr><th>รหัส</th><th>พนักงาน</th>"
                           "<th class='text-end'>NET Odoo</th><th class='text-end'>สุทธิ BPlus</th><th class='text-end'>ต่าง</th></tr>")
            for slip, c, diff in bad:
                rows += Markup("<tr><td>%s</td><td>%s</td><td class='text-end'>%s</td>"
                               "<td class='text-end'>%s</td><td class='text-end'>%s</td></tr>") % (
                    slip.employee_id.registration_number or '', slip.employee_id.name,
                    f"{slip.net_wage:,.2f}", f"{c['net']:,.2f}", f"{diff:+,.2f}")
            rows += Markup("</table>")
        if wait_loan:
            rows += Markup("<p><b>รอหักเงินกู้</b> (ยอด BPlus): %s</p>") % ", ".join(
                f"{s.employee_id.registration_number} {c['loan']:,.0f}" for s, c in wait_loan)
        return head + rows

    @staticmethod
    def _read_control_sheet(wb):
        """อ่านชีต Control ที่ bplus_extract.py สร้าง -> {รหัสพนักงาน: {earning, deduction, loan, net}} หรือ {} ถ้าไม่มี"""
        if 'Control' not in wb.sheetnames:
            return {}
        control = {}
        for idx, row in enumerate(wb['Control'].iter_rows(values_only=True), start=1):
            if idx == 1:
                continue
            row = tuple(row) + (None,) * (6 - len(row))
            reg = _cell_to_str(row[0]).upper()
            if not reg:
                continue
            control[reg] = {'earning': float(row[2] or 0), 'deduction': float(row[3] or 0),
                            'loan': float(row[4] or 0), 'net': float(row[5] or 0)}
        return control

    def action_back_to_upload(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.state = 'upload'
        self.skipped_note = False
        self.control_json = False
        self.control_note = False
        self.warning_note = False
        return self._reopen()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import Other Inputs'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _prepare_employee_slip_maps(self, batch):
        """โหลดข้อมูลครั้งเดียวก่อน loop (กัน query ต่อแถว ช้าเมื่อพนักงานหลักพัน)"""
        employees = self.env['hr.employee'].search([
            ('company_id', '=', batch.company_id.id),
            ('registration_number', '!=', False),
        ])
        emp_map = {emp.registration_number.strip().upper(): emp for emp in employees}
        slip_map = {}
        for slip in batch.slip_ids:
            slip_map.setdefault(slip.employee_id.id, []).append(slip)
        return emp_map, slip_map

    def _prepare_input_type_map(self):
        type_map = {}
        for input_type in self.env['hr.payslip.input.type'].search([]):
            if input_type.code:
                type_map.setdefault(input_type.code.strip().upper(), []).append(input_type)
        return type_map

    def _get_input_kind(self, struct, input_type, cache):
        """หาว่า input นี้ถูกใช้โดย rule ไหนใน structure และเป็นรายได้หรือรายการหัก
        คืนค่า 'earning' / 'deduction' หรือ None ถ้าไม่มี rule รองรับเลย"""
        key = (struct.id, input_type.id)
        if key not in cache:
            kind = None
            code = input_type.code or ''
            # รูปแบบการอ้างถึง input ใน python code ของ rule เช่น inputs['SSO'] / inputs["SSO"] / 'SSO' in inputs
            patterns = [f"inputs['{code}']", f'inputs["{code}"]', f"'{code}' in inputs", f'"{code}" in inputs']
            for rule in struct.rule_ids.filtered('active'):
                python_texts = (rule.amount_python_compute or '') + (rule.condition_python or '')
                referenced = (
                    rule.condition_other_input_id == input_type
                    or rule.amount_other_input_id == input_type
                    or (code and any(p in python_texts for p in patterns))
                )
                if referenced:
                    cat = rule.category_id.code
                    kind = 'deduction' if cat == 'DED' else ('company' if cat == 'COMP' else 'earning')
                    break
            cache[key] = kind
        return cache[key]


class ImportPayslipInputsWizardLine(models.TransientModel):
    _name = 'import.payslip.inputs.wizard.line'
    _description = 'Import Payslip Inputs Preview Line'
    _order = 'employee_id, kind, id'

    wizard_id = fields.Many2one('import.payslip.inputs.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    payslip_id = fields.Many2one('hr.payslip', string='Payslip', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    registration_number = fields.Char(related='employee_id.registration_number', string='Employee Code')
    input_type_id = fields.Many2one('hr.payslip.input.type', string='Input Type', required=True)
    code = fields.Char(related='input_type_id.code', string='Code')
    kind = fields.Selection([
        ('earning', 'รายได้'),
        ('deduction', 'รายการหัก'),
        ('company', 'สมทบนายจ้าง'),
    ], string='Type', required=True)
    amount = fields.Monetary(string='Amount', currency_field='currency_id')
    note = fields.Char(string='Note')
