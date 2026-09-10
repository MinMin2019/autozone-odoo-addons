from odoo import models, fields, api
from odoo.exceptions import UserError

# =================================================================================
# 1. สร้าง "สมุดจดจำ" ให้ใบ 50 ทวิ เพื่อบันทึกว่าดึงรายการบัญชีไหนมาใช้รวมบ้าง
# =================================================================================
class WithholdingTaxCert(models.Model):
    _inherit = 'withholding.tax.cert'
    
    # ฟิลด์นี้จะแอบเก็บ ID ของรายการบัญชีที่ถูกใช้ไปแล้ว
    custom_move_line_ids = fields.Many2many(
        'account.move.line', 
        relation='wht_cert_move_line_custom_rel', 
        string='Consolidated Move Lines'
    )

# =================================================================================
# 2. โค้ด Wizard ของเรา (ปรับปรุงเรื่องการเตะรายการที่ทำแล้วทิ้ง)
# =================================================================================
class WhtConsolidateWizard(models.TransientModel):
    _name = 'wht.consolidate.wizard'
    _description = 'Wizard for Consolidating WHT'

    state = fields.Selection([
        ('step1', 'กรอกเงื่อนไข'),
        ('step2', 'เลือกรายการ')
    ], default='step1', string='ขั้นตอน')

    partner_id = fields.Many2one('res.partner', string='ผู้จำหน่าย (Vendor)', required=True)
    date_from = fields.Date(string='ตั้งแต่วันที่', required=True)
    date_to = fields.Date(string='ถึงวันที่', required=True)

    wht_line_ids = fields.Many2many('account.move.line', string='รายการภาษีหัก ณ ที่จ่าย')

    def action_get_lines(self):
        tax_accounts = self.env['account.tax.repartition.line'].search([
            ('repartition_type', '=', 'tax'),
            ('account_id', '!=', False)
        ]).mapped('account_id')

        wht_accounts = tax_accounts.filtered(
            lambda a: 'หัก ณ ที่จ่าย' in a.name or 'WHT' in a.name.upper() or 'ภงด' in a.name or 'ภ.ง.ด.' in a.name or a.code.startswith('231')
        )

        # --- ท่าไม้ตายใหม่! ---
        # ไปกวาดดูว่าในใบ 50 ทวิ ที่ไม่ได้ถูกยกเลิก (state != cancel) 
        # มีการดึงรายการบัญชี (custom_move_line_ids) ตัวไหนไปใช้แล้วบ้าง
        existing_certs = self.env['withholding.tax.cert'].search([('state', '!=', 'cancel')])
        used_line_ids = existing_certs.mapped('custom_move_line_ids').ids

        move_lines = self.env['account.move.line'].search([
            ('partner_id', '=', self.partner_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('account_id', 'in', wht_accounts.ids),
            ('parent_state', '=', 'posted'),
            ('id', 'not in', used_line_ids) # <--- สั่งเตะรายการที่ทำไปแล้วทิ้งที่นี่!
        ])

        valid_lines = move_lines.filtered(lambda l: l.credit > 0 or l.debit > 0)

        if not valid_lines:
            raise UserError('ไม่พบรายการภาษีหัก ณ ที่จ่าย ที่รอทำใบ 50 ทวิ สำหรับช่วงเวลาและ Vendor ที่เลือก')

        self.write({
            'wht_line_ids': [(6, 0, valid_lines.ids)],
            'state': 'step2'
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wht.consolidate.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_back_to_step1(self):
        self.write({'state': 'step1'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wht.consolidate.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_generate_wht_cert(self):
        if not self.wht_line_ids:
            raise UserError('กรุณาเลือกรายการอย่างน้อย 1 รายการก่อนสร้างเอกสาร')

        tax_form = 'pnd53' if self.partner_id.is_company else 'pnd3'
        
        cert_line_model = self.env['withholding.tax.cert.line']
        field_def = cert_line_model._fields.get('wht_cert_income_type')
        default_income_val = False
        
        if field_def:
            if field_def.type == 'many2one':
                record = self.env[field_def.comodel_name].search([], limit=1)
                default_income_val = record.id if record else False
            elif field_def.type == 'selection':
                if isinstance(field_def.selection, list) and len(field_def.selection) > 0:
                    default_income_val = field_def.selection[0][0]
                elif callable(field_def.selection):
                    sel_list = field_def.selection(cert_line_model)
                    if sel_list:
                        default_income_val = sel_list[0][0]
            else:
                default_income_val = '5'
        
        wht_lines_data = []
        for line in self.wht_line_ids:
            wht_amount = line.credit or line.debit or 0.0
            base_amount = line.tax_base_amount if hasattr(line, 'tax_base_amount') and line.tax_base_amount else wht_amount * (100 / 3)
            
            line_dict = {
                'wht_cert_income_type': default_income_val,
                'wht_cert_income_desc': line.name or 'ค่าบริการ',
                'base': base_amount,
                'amount': wht_amount,
            }
            wht_lines_data.append((0, 0, line_dict))

        cert_val = {
            'partner_id': self.partner_id.id,
            'date': fields.Date.context_today(self),
            'income_tax_form': tax_form,
            'state': 'draft',
            'wht_line': wht_lines_data,
            # --- บันทึกความจำลงในสมุดจดจำของเรา! ---
            'custom_move_line_ids': [(6, 0, self.wht_line_ids.ids)],
        }
        
        cert_id = self.env['withholding.tax.cert'].create(cert_val)

        return {
            'name': 'หนังสือรับรองการหักภาษี ณ ที่จ่าย',
            'type': 'ir.actions.act_window',
            'res_model': 'withholding.tax.cert',
            'res_id': cert_id.id,
            'view_mode': 'form',
            'target': 'current',
        }