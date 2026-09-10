# -*- coding: utf-8 -*-
from odoo import models

# ฟิลด์เลขสินทรัพย์ถูกสร้างไว้ด้วย Odoo Studio (state=manual) จึงมีเฉพาะใน DB
# ที่เคยใช้ Studio — ต้องเช็คก่อนใช้เสมอ ไม่งั้นรายงานพังบน DB ที่ไม่มีฟิลด์
ASSET_CODE_FIELD = 'x_studio_asset_code'


class AssetsReportCustomHandler(models.AbstractModel):
    _inherit = 'account.asset.report.handler'

    def _query_lines(self, options, prefix_to_match=None, forced_account_id=None):
        lines = super()._query_lines(options, prefix_to_match=prefix_to_match, forced_account_id=forced_account_id)

        codes = {}
        asset_model = self.env['account.asset']
        if ASSET_CODE_FIELD in asset_model._fields:
            asset_ids = [asset_id for _account_id, asset_id, _group_id, _cols in lines]
            for asset in asset_model.browse(asset_ids):
                codes[asset.id] = asset[ASSET_CODE_FIELD] or ''

        for _account_id, asset_id, _group_id, cols_by_expr_label in lines:
            cols_by_expr_label['asset_code'] = codes.get(asset_id, '')
        return lines

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        # คอลัมน์ Asset Code แทรกเป็นคอลัมน์แรกใต้กลุ่ม Characteristics
        # ต้องขยาย colspan ของ subheader แรก ไม่งั้นหัวตารางชั้นบนเหลื่อมทั้งแถว
        subheaders = options.get('custom_columns_subheaders')
        if subheaders:
            subheaders[0]['colspan'] += 1
