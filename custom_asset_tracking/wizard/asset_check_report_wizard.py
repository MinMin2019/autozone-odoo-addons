# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# ฟิลด์จาก Odoo Studio (state=manual) มีเฉพาะ DB ที่เคยใช้ Studio → เช็คก่อนใช้เสมอ
ASSET_CODE_FIELD = 'x_studio_asset_code'
LOCATION_FIELD = 'x_studio_location'

# แบ่งหน้าเอง (แนวเดียวกับใบวางบิล/ใบโอน) หน่วย px ของ CSS บน A4 แนวนอน ขอบ 8/8 มม.
# (~4.55 px/มม. → พื้นที่ใช้ได้ ~880px ตั้งต่ำกว่าจริงกันล้น) แถวรายการสูงคงที่ ROW_H (template ตัดข้อความเกิน)
# ⚠️ แก้ความสูงแถว/หัว/ลายเซ็นใน template ต้องแก้ค่าคู่กันที่นี่
#   ถ้าเนื้อหาล้นไปหน้าใหม่เอง → ลด PAGE_H หรือเพิ่มค่าอื่น
PAGE_H = 860
TOP_H = 90      # ชื่อรายงาน + บริษัท + แถวสาขา/จำนวน/วันที่ (หน้าแรกของสาขาเท่านั้น)
THEAD_H = 46    # หัวตาราง 2 ชั้น (ทุกหน้า)
GROUP_H = 24    # แถวชื่อหมวด
ROW_H = 54      # แถวทรัพย์สิน
END_H = 185     # สรุปผล + ลายเซ็น (หน้าสุดท้าย)


class AssetCheckReportWizard(models.TransientModel):
    _name = 'az.asset.check.report.wizard'
    _description = 'Asset Check Report Wizard'

    branch_ids = fields.Many2many(
        'account.analytic.account',
        string='Branch',
        help='สาขา (Main Analytic ของสินทรัพย์) — ว่าง = ทุกสาขา',
    )
    custodian_ids = fields.Many2many(
        'hr.employee',
        string='Custodian',
        context={'active_test': False},
        help='ผู้รับผิดชอบทรัพย์สิน — ว่าง = ทุกคนในสาขาที่เลือก',
    )
    include_no_custodian = fields.Boolean(
        string='Include assets without custodian',
        default=True,
        help='รวมทรัพย์สินที่ยังไม่ระบุผู้รับผิดชอบ (แยกเป็นชุด "ไม่ระบุผู้รับผิดชอบ")',
    )
    asset_ids = fields.Many2many(
        'account.asset',
        string='Selected Assets',
        help='เปิดจากลิสต์สินทรัพย์ → พิมพ์เฉพาะรายการที่ติ๊ก',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        if ctx.get('active_model') == 'account.asset' and ctx.get('active_ids'):
            res['asset_ids'] = [(6, 0, ctx['active_ids'])]
        return res

    def _get_assets(self):
        self.ensure_one()
        domain = [('state', 'in', ('draft', 'open', 'paused'))]
        if self.asset_ids:
            domain.append(('id', 'in', self.asset_ids.ids))
        if self.branch_ids:
            domain.append(('main_analytic_account_id', 'in', self.branch_ids.ids))
        if self.custodian_ids:
            if self.include_no_custodian:
                domain += ['|', ('custodian_id', 'in', self.custodian_ids.ids), ('custodian_id', '=', False)]
            else:
                domain.append(('custodian_id', 'in', self.custodian_ids.ids))
        elif not self.include_no_custodian:
            domain.append(('custodian_id', '!=', False))
        return self.env['account.asset'].search(domain)

    def action_print(self):
        self.ensure_one()
        if not (self.asset_ids or self.branch_ids or self.custodian_ids):
            raise UserError(_('กรุณาเลือกสาขา หรือ ผู้รับผิดชอบ อย่างน้อย 1 อย่าง'))
        assets = self._get_assets()
        if not assets:
            raise UserError(_('ไม่พบทรัพย์สินตามเงื่อนไขที่เลือก'))
        return self.env.ref('custom_asset_tracking.action_report_asset_check').report_action(
            None, data={'asset_ids': assets.ids},
        )


class AssetCheckReport(models.AbstractModel):
    _name = 'report.custom_asset_tracking.report_asset_check'
    _description = 'Asset Check Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        asset_ids = (data or {}).get('asset_ids') or docids or []
        assets = self.env['account.asset'].browse(asset_ids).exists()
        Asset = self.env['account.asset']
        has_code = ASSET_CODE_FIELD in Asset._fields
        has_location = LOCATION_FIELD in Asset._fields

        def code_of(asset):
            return (asset[ASSET_CODE_FIELD] or '') if has_code else ''

        # 1 ชุดเอกสาร = 1 สาขา (ขึ้นหน้าใหม่ทุกสาขา) ผู้ถือครองทุกคนรวมในตารางเดียว
        sections = {}
        for asset in assets:
            sections.setdefault(asset.main_analytic_account_id, self.env['account.asset'])
            sections[asset.main_analytic_account_id] |= asset

        # ชื่อผู้ถือครองอ่านจาก hr.employee.public — user บัญชีส่วนใหญ่ไม่มีสิทธิ์ HR
        # อ่าน hr.employee ตรง ๆ แล้ว prefetch ไปโดนฟิลด์ที่ไม่มีในโปรไฟล์สาธารณะ → AccessError
        names = {
            emp.id: emp.name
            for emp in self.env['hr.employee.public'].with_context(active_test=False).browse(
                assets.custodian_id.ids)
        }

        docs = []
        for branch in sorted(sections, key=lambda b: b.name or '~'):
            # หมวด (Asset Model) เรียงตามเลขบัญชีสินทรัพย์ของหมวด (171000 ที่ดิน → 173001 อาคาร → ...)
            # ไม่มีหมวด → ท้ายสุด
            section_assets = sections[branch].sorted(
                lambda a: (not a.model_id, a.model_id.account_asset_id.code or '~',
                           a.model_id.name or '', code_of(a), a.name or '')
            )
            groups = []
            seq = 0
            for asset in section_assets:
                group_name = asset.model_id.name or _('ไม่ระบุหมวด')
                if not groups or groups[-1]['name'] != group_name:
                    groups.append({'name': group_name, 'lines': []})
                seq += 1
                groups[-1]['lines'].append({
                    'seq': seq,
                    'asset': asset,
                    'code': code_of(asset),
                    'custodian': names.get(asset.custodian_id.id, ''),
                    'location': (asset[LOCATION_FIELD] or '') if has_location else '',
                })
            docs.append({
                'company': section_assets[:1].company_id or self.env.company,
                'branch': branch,
                'count': len(section_assets),
                'pages': self._paginate(groups),
            })

        return {
            'doc_ids': assets.ids,
            'doc_model': 'account.asset',
            'docs': docs,
            'print_date': fields.Date.context_today(self),
        }

    @api.model
    def _paginate(self, groups):
        """แบ่งแถวเป็นหน้า: [[{'type': 'group'|'line', ...}, ...], ...]
        - เริ่มหน้าใหม่กลางหมวด → ใส่แถวชื่อหมวดซ้ำ (ต่อ)
        - ชื่อหมวดไม่ค้างท้ายหน้าโดยไม่มีรายการตาม
        - หน้าสุดท้ายต้องมีที่ให้สรุป+ลายเซ็น ไม่พอ → ยกรายการสุดท้ายไปหน้าใหม่ด้วย
          (ไม่ให้หน้าลายเซ็นโล่งไม่มีรายการ)
        """
        pages = [[]]
        used = TOP_H + THEAD_H

        def group_row(group, cont):
            return {'type': 'group', 'name': group['name'], 'count': len(group['lines']), 'cont': cont}

        for group in groups:
            for idx, line in enumerate(group['lines']):
                need_head = idx == 0 or not pages[-1]
                cost = ROW_H + (GROUP_H if need_head else 0)
                if used + cost > PAGE_H and pages[-1]:
                    pages.append([])
                    used = THEAD_H
                    need_head = True
                    cost = ROW_H + GROUP_H
                if need_head:
                    pages[-1].append(group_row(group, cont=idx > 0))
                line.update(type='line', group=group)
                pages[-1].append(line)
                used += cost

        if used + END_H > PAGE_H:
            last = pages[-1]
            line = last.pop()
            if last and last[-1]['type'] == 'group':
                last.pop()  # ชื่อหมวดที่ค้างท้ายหน้า ย้ายตามไปด้วย
            if not last:
                pages.pop()
            group = line['group']
            pages.append([group_row(group, cont=line is not group['lines'][0]), line])
        return pages

