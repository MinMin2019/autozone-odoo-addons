# Override ของ account_reports._inject_report_into_xlsx_sheet (คัดลอกทั้ง method จาก
# odoo18ent/account_reports/models/account_report.py แล้วแทรกการเขียนสูตร =SUM)
# เหตุที่ต้องคัดลอก: จุดเขียนเซลล์เป็น closure ภายใน method ไม่มี hook ให้ต่อ
# ถ้า upgrade core ต้องเทียบ method ต้นทางใหม่ทุกครั้ง
from odoo import _, models


def _col_letter(col_index):
    letters = ""
    col_index += 1
    while col_index:
        col_index, rem = divmod(col_index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


class AccountReport(models.AbstractModel):
    _inherit = "account.report"

    def _azs_numeric(self, column):
        value = column.get("name", "")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        return None

    def _azs_build_xlsx_sum_plan(self, lines, y_offset_start, original_x_offset):
        """คืน dict {(line_index, col_index): formula} สำหรับแถวยอดรวมที่พิสูจน์ได้ว่า
        ค่า = ผลบวกของแถวลูกโดยตรง (เทียบภายใน 0.02) — แถวที่ยอดไม่ใช่ผลบวกตรง ๆ
        (สูตรพิเศษของ report engine) จะไม่ถูกแตะ คงเป็นตัวเลขเดิม"""
        rows = []
        y_offset = y_offset_start
        for y, line in enumerate(lines):
            if line.get("level") == 0:
                y_offset += 1
            rows.append(y + y_offset)

        def markup_of(line):
            parsed = self._parse_line_id(line.get("id"))
            return parsed[-1][0] if parsed else None

        markups = [markup_of(line) for line in lines]
        # parent_id ที่ชี้ไป root ของรายงาน (ไม่ใช่แถวจริงในชีต เช่น Trial Balance) นับเป็น top-level
        real_line_ids = {line.get("id") for line in lines}
        children_by_parent = {}
        top_level = []
        for idx, line in enumerate(lines):
            if markups[idx] == "total":
                continue
            parent = line.get("parent_id")
            if parent and parent in real_line_ids:
                children_by_parent.setdefault(parent, []).append(idx)
            else:
                top_level.append(idx)

        plan = {}
        for idx, line in enumerate(lines):
            if markups[idx] == "total":
                parent = line.get("parent_id")
                if parent and parent in real_line_ids:
                    operands = children_by_parent.get(parent, [])
                else:
                    operands = top_level
            else:
                operands = children_by_parent.get(line.get("id"), [])
            operands = [j for j in operands if j != idx]
            if not operands:
                continue

            n_cols = len(line.get("columns", []))
            x_shift = line.get("colspan", 1) - 1
            for c in range(n_cols):
                total_value = self._azs_numeric(line["columns"][c])
                if total_value is None:
                    continue
                x_total = original_x_offset + 1 + c + x_shift
                operand_rows = []
                operand_sum = 0.0
                x_mismatch = False
                for j in operands:
                    op_line = lines[j]
                    if c >= len(op_line.get("columns", [])):
                        continue
                    if original_x_offset + 1 + c + (op_line.get("colspan", 1) - 1) != x_total:
                        x_mismatch = True
                        break
                    value = self._azs_numeric(op_line["columns"][c])
                    if value is not None:
                        operand_sum += value
                    operand_rows.append(rows[j])
                if x_mismatch or not operand_rows or abs(total_value - operand_sum) > 0.02:
                    continue

                # ยุบแถวติดกันเป็นช่วง A5:A9 ให้สูตรสั้น
                operand_rows.sort()
                parts = []
                start = prev = operand_rows[0]
                for row in operand_rows[1:]:
                    if row == prev + 1:
                        prev = row
                        continue
                    parts.append((start, prev))
                    start = prev = row
                parts.append((start, prev))
                if len(parts) > 100:
                    continue
                letter = _col_letter(x_total)
                refs = [
                    f"{letter}{a + 1}" if a == b else f"{letter}{a + 1}:{letter}{b + 1}"
                    for a, b in parts
                ]
                plan[(idx, c)] = "=SUM({})".format(",".join(refs))
        return plan

    def _inject_report_into_xlsx_sheet(self, options, workbook, sheet):
        fonts = self._get_xlsx_export_fonts()

        def write_cell(sheet, x, y, value, style, colspan=1, datetime=False):
            self._set_xlsx_cell_sizes(sheet, fonts, x, y, value, style, colspan > 1)
            if colspan == 1:
                if datetime:
                    sheet.write_datetime(y, x, value, style)
                else:
                    sheet.write(y, x, value, style)
            else:
                sheet.merge_range(y, x, y, x + colspan - 1, value, style)

        default_format_props = {'font_name': 'Lato', 'font_size': 12, 'font_color': '#666666', 'num_format': '#,##0.00'}
        text_format_props = {'font_name': 'Lato', 'font_size': 12, 'font_color': '#666666'}
        date_format_props = {'font_name': 'Lato', 'font_size': 12, 'font_color': '#666666', 'align': 'left', 'num_format': 'yyyy-mm-dd'}
        title_format = workbook.add_format({'font_name': 'Lato', 'font_size': 12, 'bold': True, 'bottom': 2})
        annotation_format = workbook.add_format({**text_format_props, 'text_wrap': True})
        workbook_formats = {
            0: {
                'default': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 6}),
                'text': workbook.add_format({**text_format_props, 'bold': True, 'font_size': 13, 'bottom': 6}),
                'date': workbook.add_format({**date_format_props, 'bold': True, 'font_size': 13, 'bottom': 6}),
                'total': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 6}),
            },
            1: {
                'default': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 1}),
                'text': workbook.add_format({**text_format_props, 'bold': True, 'font_size': 13, 'bottom': 1}),
                'date': workbook.add_format({**date_format_props, 'bold': True, 'font_size': 13, 'bottom': 1}),
                'total': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 1}),
                'default_indent': workbook.add_format({**default_format_props, 'bold': True, 'font_size': 13, 'bottom': 1, 'indent': 1}),
                'date_indent': workbook.add_format({**date_format_props, 'bold': True, 'font_size': 13, 'bottom': 1, 'indent': 1}),
            },
            2: {
                'default': workbook.add_format({**default_format_props, 'bold': True}),
                'text': workbook.add_format({**text_format_props, 'bold': True}),
                'date': workbook.add_format({**date_format_props, 'bold': True}),
                'initial': workbook.add_format(default_format_props),
                'total': workbook.add_format({**default_format_props, 'bold': True}),
                'default_indent': workbook.add_format({**default_format_props, 'bold': True, 'indent': 2}),
                'date_indent': workbook.add_format({**date_format_props, 'bold': True, 'indent': 2}),
                'initial_indent': workbook.add_format({**default_format_props, 'indent': 2}),
                'total_indent': workbook.add_format({**default_format_props, 'bold': True, 'indent': 1}),
            },
            'default': {
                'default': workbook.add_format(default_format_props),
                'text': workbook.add_format(text_format_props),
                'date': workbook.add_format(date_format_props),
                'total': workbook.add_format(default_format_props),
                'default_indent': workbook.add_format({**default_format_props, 'indent': 2}),
                'date_indent': workbook.add_format({**date_format_props, 'indent': 2}),
                'total_indent': workbook.add_format({**default_format_props, 'indent': 2}),
            },
        }

        def get_format(content_type='default', level='default'):
            if isinstance(level, int) and level not in workbook_formats:
                workbook_formats[level] = {
                    **workbook_formats['default'],
                    'default_indent': workbook.add_format({**default_format_props, 'indent': level}),
                    'date_indent': workbook.add_format({**date_format_props, 'indent': level}),
                    'total_indent': workbook.add_format({**default_format_props, 'bold': True, 'indent': level - 1}),
                }

            level_formats = workbook_formats[level]
            if '_indent' in content_type and not level_formats.get(content_type):
                return level_formats.get('default_indent', level_formats.get(content_type.removesuffix('_indent'), level_formats['default']))
            return level_formats.get(content_type, level_formats['default'])

        print_mode_self = self.with_context(no_format=True)
        lines = self._filter_out_folded_children(print_mode_self._get_lines(options))
        annotations = self.get_annotations(options)

        # For reports with lines generated for accounts, the account name and codes are shown in a single column.
        # To help user post-process the report if they need, we should in such a case split the account name and code in two columns.
        account_lines_split_names = {}
        for line in lines:
            line_model = self._get_model_info_from_id(line['id'])[0]
            if line_model == 'account.account':
                # Reuse the _split_code_name to split the name and code in two values.
                account_lines_split_names[line['id']] = self.env['account.account']._split_code_name(line['name'])

        # Set the (Account) Name column width to 50.
        # If we have account lines and split the name and code in two columns, we will also set the code column.
        if len(account_lines_split_names) > 0:
            sheet.set_column(0, 0, 13)
            sheet.set_column(1, 1, 50)
        else:
            sheet.set_column(0, 0, 50)

        if not options.get('no_xlsx_currency_code_columns'):
            self._add_xlsx_currency_codes_columns(options, lines)

        original_x_offset = 1 if len(account_lines_split_names) > 0 else 0

        y_offset = 0
        # 1 and not 0 to leave space for the line name. original_x_offset allows making place for the code column if needed.
        x_offset = original_x_offset + 1

        # Add headers.
        # For this, iterate in the same way as done in main_table_header template
        column_headers_render_data = self._get_column_headers_render_data(options)
        for header_level_index, header_level in enumerate(options['column_headers']):
            for header_to_render in header_level * column_headers_render_data['level_repetitions'][header_level_index]:
                colspan = header_to_render.get('colspan', column_headers_render_data['level_colspan'][header_level_index])
                write_cell(sheet, x_offset, y_offset, header_to_render.get('name', ''), title_format, colspan + (1 if options['show_horizontal_group_total'] and header_level_index == 0 else 0))
                x_offset += colspan
            if options.get('column_percent_comparison') == 'growth':
                write_cell(sheet, x_offset, y_offset, '%', title_format)
                x_offset += 1

            if options['show_horizontal_group_total'] and header_level_index != 0:
                horizontal_group_name = next((group['name'] for group in options['available_horizontal_groups'] if group['id'] == options['selected_horizontal_group_id']), None)
                write_cell(sheet, x_offset, y_offset, horizontal_group_name, title_format)
                x_offset += 1
            if annotations:
                annotations_x_offset = x_offset
                write_cell(sheet, annotations_x_offset, y_offset, 'Annotations', title_format)
                x_offset += 1
            y_offset += 1
            x_offset = original_x_offset + 1

        for subheader in column_headers_render_data['custom_subheaders']:
            colspan = subheader.get('colspan', 1)
            write_cell(sheet, x_offset, y_offset, subheader.get('name', ''), title_format, colspan)
            x_offset += colspan
        y_offset += 1
        x_offset = original_x_offset + 1

        if account_lines_split_names:
            # If we have a separate account code column, add a title for it
            write_cell(sheet, x_offset - 2, y_offset, _("Code"), title_format)
            write_cell(sheet, x_offset - 1, y_offset, _("Account Name"), title_format)
        sheet.set_column(x_offset, x_offset + len(options['columns']), 10)

        for column in options['columns']:
            colspan = column.get('colspan', 1)
            write_cell(sheet, x_offset, y_offset, column.get('name', ''), title_format, colspan)
            x_offset += colspan

        if options['show_horizontal_group_total']:
            write_cell(sheet, x_offset, y_offset, options['columns'][0].get('name', ''), title_format, colspan)

        if options.get('column_percent_comparison') == 'growth':
            write_cell(sheet, x_offset, y_offset, '', title_format, colspan)
        y_offset += 1

        if options.get('order_column'):
            lines = self.sort_lines(lines, options)

        # จุดแทรก: วางแผนสูตร SUM หลัง lines นิ่งแล้ว (ผ่าน sort) และรู้แถวเริ่มข้อมูล
        sum_plan = self._azs_build_xlsx_sum_plan(lines, y_offset, original_x_offset)

        # Disable bold styling for the max level.
        max_level = max(line.get('level', -1) for line in lines) if lines else -1
        if max_level in {0, 1, 2}:
            # Total lines are supposed to be a level above, so we don't touch them.
            for wb_format in (s for s in workbook_formats[max_level] if 'total' not in s):
                workbook_formats[max_level][wb_format].set_bold(False)

        # Add lines.
        counter = 1
        for y, line in enumerate(lines):
            level = line.get('level')
            if level == 0:
                y_offset += 1
            elif not level:
                level = 'default'

            line_id = self._parse_line_id(line.get('id'))
            is_initial_line = line_id[-1][0] == 'initial' if line_id else False
            is_total_line = line_id[-1][0] == 'total' if line_id else False

            # Write the first column(s), with a specific style to manage the indentation.
            cell_type, cell_value = self._get_cell_type_value(line)
            account_code_cell_format = get_format('text', level)

            if cell_type == 'date':
                cell_format = get_format('date_indent', level)
            elif is_initial_line:
                cell_format = get_format('initial_indent', level)
            elif is_total_line:
                cell_format = get_format('total_indent', level)
            else:
                cell_format = get_format('default_indent', level)

            x_offset = original_x_offset + 1
            if lines[y]['id'] in account_lines_split_names:
                # Write the Account Code and Name columns.
                code, name = account_lines_split_names[lines[y]['id']]
                # Don't indent the account code and don't format is as a monetary value either.
                write_cell(sheet, 0, y + y_offset, code, account_code_cell_format)
                write_cell(sheet, 1, y + y_offset, name, cell_format)
            else:
                write_cell(sheet, original_x_offset, y + y_offset, cell_value, cell_format, datetime=cell_type == 'date')

                if 'parent_id' in line and line['parent_id'] in account_lines_split_names:
                    write_cell(sheet, 1 + original_x_offset, y + y_offset, account_lines_split_names[line['parent_id']][0], account_code_cell_format)
                elif account_lines_split_names:
                    write_cell(sheet, 1 + original_x_offset, y + y_offset, "", account_code_cell_format)

            # Write all the remaining cells.
            columns = line['columns']
            if options.get('column_percent_comparison') and 'column_percent_comparison_data' in line:
                columns += [line['column_percent_comparison_data']]

            if options['show_horizontal_group_total']:
                columns += [line.get('horizontal_group_total_data', {'name': 0})]
            for x, column in enumerate(columns, start=x_offset):
                cell_type, cell_value = self._get_cell_type_value(column)
                if cell_type == 'date':
                    cell_format = get_format('date', level)
                elif is_initial_line:
                    cell_format = get_format('initial', level)
                elif is_total_line:
                    cell_format = get_format('total', level)
                else:
                    cell_format = get_format('default', level)

                # จุดแทรก: เซลล์ยอดรวมที่พิสูจน์แล้วเขียนเป็นสูตร (เก็บค่าเดิมเป็น cached value)
                formula = sum_plan.get((y, x - x_offset)) if cell_type != 'date' else None
                if formula:
                    target_x = x + line.get('colspan', 1) - 1
                    self._set_xlsx_cell_sizes(sheet, fonts, target_x, y + y_offset, cell_value, cell_format, False)
                    sheet.write_formula(y + y_offset, target_x, formula, cell_format, cell_value)
                else:
                    write_cell(sheet, x + line.get('colspan', 1) - 1, y + y_offset, cell_value, cell_format, datetime=cell_type == 'date')

            # Write annotations.
            if annotations and (line_annotations := annotations.get(line['id'])):
                line_annotation_text = []
                for line_annotation in line_annotations:
                    line_annotation_text.append(f"{counter} - {line_annotation['text']}")
                    counter += 1
                write_cell(sheet, annotations_x_offset, y + y_offset, "\n".join(line_annotation_text), annotation_format)
