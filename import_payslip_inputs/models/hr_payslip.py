# -*- coding: utf-8 -*-
from collections import defaultdict

from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, plaintext2html


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _legacy_structures(self):
        """โครงสร้างเงินเดือนของโมดูลนี้ (Legacy/โรงงาน/สำนักงาน/ผู้บริหาร) — ยอดทุกบรรทัดมาจากการ import"""
        ids = self.env['ir.model.data'].sudo().search([
            ('module', '=', 'import_payslip_inputs'),
            ('model', '=', 'hr.payroll.structure'),
        ]).mapped('res_id')
        return self.env['hr.payroll.structure'].browse(ids)

    def action_payslip_done(self):
        # กันกด "Create Draft Entry" ก่อน import: สลิปโครงสร้าง Legacy ที่ยังไม่มีรายการจากไฟล์/BPlus
        # จะได้ยอด 0 หรือยอดค้างจากที่กรอกมือ แล้วลงบัญชีผิดทั้งก้อน
        legacy = self._legacy_structures()
        not_imported = self.filtered(
            lambda s: s.struct_id in legacy and not s.input_line_ids.filtered('is_imported'))
        if not_imported:
            names = '\n'.join('- %s' % n for n in not_imported[:15].mapped('employee_id.name'))
            more = len(not_imported) - 15
            if more > 0:
                names += '\n' + _('... และอีก %s คน', more)
            raise UserError(_(
                "ยังไม่ได้นำเข้ายอดเงินเดือน %(count)s สลิป จึงยังสร้างรายการบัญชีไม่ได้\n"
                "กรุณากด \"Import Inputs (Excel)\" บน Payslip Batch แล้วดึงจาก Business Plus ก่อน\n\n%(names)s",
                count=len(not_imported), names=names))
        return super().action_payslip_done()

    def _action_create_account_move(self):
        # สลิปโครงสร้าง Legacy: แยกใบสำคัญ 1 ใบต่อสาขา (Analytic บนสัญญาจ้าง) — บัญชีขอให้แยกใบรายสาขา
        # ทำของเราก่อน (ได้ move_id แล้ว) จากนั้น super จะกรอง not slip.move_id เหลือเฉพาะสลิปโครงสร้างอื่น
        all_payslips = self
        for run in self.payslip_run_id:
            if run._are_payslips_ready():
                all_payslips |= run.slip_ids
        legacy_structs = self._legacy_structures()
        legacy = all_payslips.filtered(
            lambda s: s.state == 'done' and not s.move_id and s.struct_id in legacy_structs)
        if legacy:
            legacy._create_branch_account_moves()
        return super()._action_create_account_move()

    def _create_branch_account_moves(self):
        """ดัดแปลงจาก hr_payroll_account _action_create_account_move: จัดกลุ่ม (สมุดรายวัน, เดือน, สาขา)
        แทน (สมุดรายวัน, เดือน) — ยอดในแต่ละใบลงตัวเองเพราะทุกบรรทัดของสลิปถือ Analytic สาขาเดียวกัน"""
        precision = self.env['decimal.precision'].precision_get('Payroll')
        if any(not structure.journal_id for structure in self.mapped('struct_id')):
            raise UserError(_('One of the payroll structures has no account journal defined on it.'))

        groups = defaultdict(lambda: self.env['hr.payslip'])
        for slip in self:
            date = slip.date or fields.Date.end_of(slip.date_to, 'month')
            groups[(slip.struct_id.journal_id.id, date, slip.contract_id.analytic_account_id)] |= slip

        def sort_key(key):
            branch = key[2]
            return (key[0], key[1], branch.code or branch.name or '')

        account_move_vals = []
        slips_date_tuples = []
        for key in sorted(groups, key=sort_key):
            journal_id, date, branch = key
            slips = groups[key]
            month = fields.Date.end_of(slips[0].date_to, 'month').strftime('%B %Y')
            branch_label = branch.code or branch.name or _('ไม่ระบุสาขา')
            move_dict = {
                'narration': '',
                'ref': '%s - %s' % (month, branch_label),
                'journal_id': journal_id,
                'date': date,
            }
            line_ids = []
            for slip in slips:
                move_dict['narration'] += plaintext2html('%s - %s' % (slip.number or '', slip.employee_id.name or ''))
                move_dict['narration'] += Markup('<br/>')
                line_ids.extend(slip._prepare_slip_lines(date, line_ids))

            debit_sum = sum(line['debit'] for line in line_ids)
            credit_sum = sum(line['credit'] for line in line_ids)
            if float_compare(credit_sum, debit_sum, precision_digits=precision) == -1:
                slips[-1]._prepare_adjust_line(line_ids, 'credit', debit_sum, credit_sum, date)
            elif float_compare(debit_sum, credit_sum, precision_digits=precision) == -1:
                slips[-1]._prepare_adjust_line(line_ids, 'debit', debit_sum, credit_sum, date)

            move_dict['line_ids'] = [(0, 0, line_vals) for line_vals in line_ids]
            account_move_vals.append(move_dict)
            slips_date_tuples.append((slips, date))

        moves = self._create_account_move(account_move_vals)
        for move, (slips, date) in zip(moves, slips_date_tuples):
            slips.write({'move_id': move.id, 'date': date})
            # Batch เก็บได้ใบเดียว (ปุ่ม Journal Entry) — ใส่ใบแรก, action_open_move ของ Batch เปิดครบทุกใบ
            slips.payslip_run_id.filtered(lambda r: not r.move_id).write({'move_id': move.id})
        return moves


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_open_move(self):
        moves = self.slip_ids.move_id
        if len(moves) <= 1:
            return super().action_open_move()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }
