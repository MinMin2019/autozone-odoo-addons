# -*- coding: utf-8 -*-
from odoo import models, _

# ค่า assets_grouping_field ที่โมดูลนี้เพิ่ม (ตรงกับ optionValue ใน groupby.xml)
GROUPING_FIELD_CLASS = 'x_class_id'


class AssetsReportClassHandler(models.AbstractModel):
    _inherit = 'account.asset.report.handler'

    def _query_lines(self, options, prefix_to_match=None, forced_account_id=None):
        lines = super()._query_lines(options, prefix_to_match=prefix_to_match, forced_account_id=forced_account_id)

        asset_ids = [asset_id for _account_id, asset_id, _group_id, _cols in lines]
        assets = self.env['account.asset'].browse(asset_ids)

        # รวบรวม analytic account id ทั้งหมดจาก distribution ก่อน แล้ว browse ทีเดียว
        # (key ของ distribution เป็น string อาจเป็น "54" หรือ "3,54" กรณีข้าม plan)
        all_analytic_ids = set()
        for asset in assets:
            for key in (asset.analytic_distribution or {}):
                all_analytic_ids.update(int(account_id) for account_id in key.split(','))
        analytic_names = {
            account.id: account.display_name
            for account in self.env['account.analytic.account'].browse(all_analytic_ids)
        }

        labels = {}
        for asset in assets:
            distribution = asset.analytic_distribution or {}
            parts = []
            for key, percentage in sorted(distribution.items(), key=lambda item: -item[1]):
                names = ', '.join(analytic_names.get(int(account_id), '?') for account_id in key.split(','))
                if len(distribution) == 1 and percentage == 100:
                    parts.append(names)
                else:
                    parts.append(f"{percentage:g}% {names}")
            labels[asset.id] = ' + '.join(parts)

        for _account_id, asset_id, _group_id, cols_by_expr_label in lines:
            cols_by_expr_label['analytic'] = labels.get(asset_id, '')
        return lines

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        # คอลัมน์ Analytic อยู่ใต้กลุ่ม Characteristics ต้องขยาย colspan ของ
        # subheader แรก (แบบเดียวกับ custom_asset_report_code)
        subheaders = options.get('custom_columns_subheaders')
        if subheaders:
            subheaders[0]['colspan'] += 1

    def _generate_report_lines_without_grouping(self, report, options, prefix_to_match=None, parent_id=None, forced_account_id=None):
        lines, totals_by_column_group = super()._generate_report_lines_without_grouping(
            report, options, prefix_to_match=prefix_to_match, parent_id=parent_id, forced_account_id=forced_account_id,
        )

        # ฝัง class (analytic account) ของแต่ละสินทรัพย์ไว้บนบรรทัด เพื่อให้
        # _group_by_field ใช้จัดกลุ่มได้ — ต้องทำก่อน _group_by_field เขียนทับ line id
        asset_ids = [report._get_model_info_from_id(line['id'])[1] for line in lines]
        class_by_asset = {
            asset.id: asset.x_class_id.id
            for asset in self.env['account.asset'].browse(asset_ids)
        }
        for line, asset_id in zip(lines, asset_ids):
            line['assets_class_id'] = class_by_asset.get(asset_id) or None

        return lines, totals_by_column_group

    def _group_by_field(self, report, lines, options):
        if options['assets_grouping_field'] != GROUPING_FIELD_CLASS:
            return super()._group_by_field(report, lines, options)

        # โครงเดียวกับ _group_by_field ของ account_asset แต่ parent เป็น
        # analytic account จากฟิลด์ Class แทนบัญชี/กลุ่มสินทรัพย์
        if not lines:
            return lines

        parent_model = 'account.analytic.account'
        line_vals_per_class_id = {}
        for line in lines:
            class_id = line.get('assets_class_id')
            _model, res_id = report._get_model_info_from_id(line['id'])
            line['id'] = report._build_line_id([
                (None, parent_model, class_id),
                (None, 'account.asset', res_id),
            ])

            is_parent_in_unfolded_lines = any(
                report._get_model_info_from_id(unfolded_line_id) == (parent_model, class_id)
                for unfolded_line_id in options.get('unfolded_lines')
            )
            line_vals_per_class_id.setdefault(class_id, {
                'id': report._build_line_id([(None, parent_model, class_id)]),
                'columns': [],  # Filled later
                'unfoldable': True,
                'unfolded': is_parent_in_unfolded_lines or options.get('unfold_all'),
                'level': 1,
                'group_lines': [],
            })['group_lines'].append(line)

        class_names = {
            record.id: record.display_name
            for record in self.env[parent_model].browse([cid for cid in line_vals_per_class_id if cid])
        }

        rslt_lines = []
        idx_monetary_columns = [idx_col for idx_col, col in enumerate(options['columns']) if col['figure_type'] == 'monetary']

        # เรียงกลุ่มตามชื่อคลาส, สินทรัพย์ไม่ระบุคลาสไปกองท้ายสุด
        for class_id in sorted(line_vals_per_class_id, key=lambda cid: (not cid, class_names.get(cid, ''))):
            parent_line_vals = line_vals_per_class_id[class_id]
            parent_line_vals['name'] = class_names.get(class_id) or _("(No Class)")
            rslt_lines.append(parent_line_vals)

            group_totals = {column_index: 0 for column_index in idx_monetary_columns}
            group_lines = report._regroup_lines_by_name_prefix(
                options,
                parent_line_vals.pop('group_lines'),
                '_report_expand_unfoldable_line_assets_report_prefix_group',
                parent_line_vals['level'],
                parent_line_dict_id=parent_line_vals['id'],
            )

            for parent_subline in group_lines:
                for column_index in idx_monetary_columns:
                    group_totals[column_index] += parent_subline['columns'][column_index].get('no_format', 0)
                parent_subline['parent_id'] = parent_line_vals['id']
                rslt_lines.append(parent_subline)

            for column_index in range(len(options['columns'])):
                parent_line_vals['columns'].append(report._build_column_dict(
                    group_totals.get(column_index, ''),
                    options['columns'][column_index],
                    options=options,
                ))

        return rslt_lines
