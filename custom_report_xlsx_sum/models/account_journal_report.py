# Override ของ account.journal.report.handler.export_to_xlsx (คัดลอกทั้ง method จาก
# odoo18ent/account_reports/models/account_journal_report.py แล้วเขียนแถว Total เป็นสูตร =SUM)
# เหตุที่ต้องคัดลอก: แถว Total ถูกเขียนกลางลูปยาว ไม่มี hook ให้ต่อ
import datetime
import io
import re

from collections import defaultdict

from PIL import ImageFont

from odoo import _, models
from odoo.tools.misc import file_path, xlsxwriter

from odoo.addons.account_reports.models.account_journal_report import (
    XLSX_BORDER_COLOR,
    XLSX_FONT_SIZE_DEFAULT,
    XLSX_FONT_SIZE_HEADING,
    XLSX_GRAY_200,
)

from .account_report import _col_letter


def _parse_money(value):
    """แปลงข้อความเงินที่ format แล้ว เช่น '1,234.50\xa0฿' → (1234.5, '\xa0฿')
    คืน None ถ้าไม่ใช่รูปแบบเงิน (suffix คือส่วนสกุลเงินท้ายข้อความ เก็บไว้ทำ num_format)"""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(-?[\d,]+\.\d+)(\D*)", value.strip())
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "")), match.group(2)
    except ValueError:
        return None


class JournalReportCustomHandler(models.AbstractModel):
    _inherit = "account.journal.report.handler"

    def _azs_money_format(self, workbook, cache, suffix, bold, bg_color, border_top, border_bottom, border_color):
        key = (suffix, bold, bg_color, border_top, border_bottom)
        if key not in cache:
            cache[key] = workbook.add_format({
                'font_name': 'Arial',
                'font_size': XLSX_FONT_SIZE_DEFAULT,
                'bold': bold,
                'bg_color': bg_color,
                'align': 'right',
                'bottom': border_bottom,
                'top': border_top,
                'border_color': border_color,
                'num_format': '#,##0.00"%s"' % suffix if suffix else '#,##0.00',
            })
        return cache[key]

    def export_to_xlsx(self, options, response=None):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {
            'in_memory': True,
            'strings_to_formulas': False,
        })
        report = self.env['account.report'].search([('id', '=', options['report_id'])], limit=1)
        print_options = report.get_options(previous_options={**options, 'export_mode': 'print'})
        document_data = self._generate_document_data_for_export(report, print_options, 'xlsx')

        # We need to use fonts to calculate column width otherwise column width would be ugly
        # Using Lato as reference font is a hack and is not recommended. Customer computers don't have this font by default and so
        # the generated xlsx wouldn't have this font. Since it is not by default, we preferred using Arial font as default and keep
        # Lato as reference for columns width calculations.
        fonts = {}
        for font_size in (XLSX_FONT_SIZE_HEADING, XLSX_FONT_SIZE_DEFAULT):
            fonts[font_size] = defaultdict()
            for font_type in ('Reg', 'Bol', 'RegIta', 'BolIta'):
                try:
                    lato_path = f'web/static/fonts/lato/Lato-{font_type}-webfont.ttf'
                    fonts[font_size][font_type] = ImageFont.truetype(file_path(lato_path), font_size)
                except (OSError, FileNotFoundError):
                    # This won't give great result, but it will work.
                    fonts[font_size][font_type] = ImageFont.load_default()

        money_format_cache = {}

        for journal_vals in document_data['journals_vals']:
            cursor_x = 0
            cursor_y = 0

            # Default sheet properties
            sheet = workbook.add_worksheet(journal_vals['name'][:31])
            columns = journal_vals['columns']
            # คอลัมน์เงิน (ชิดขวา) จะถูกเขียนเป็นตัวเลขจริงแทนข้อความ เพื่อให้สูตร SUM ใช้ได้
            money_labels = {c['label'] for c in columns if 'o_right_alignment' in c.get('class', '')}

            for column in columns:
                align = 'left'
                if 'o_right_alignment' in column.get('class', ''):
                    align = 'right'
                self._write_cell(cursor_x, cursor_y, column['name'], 1, False, report, fonts, workbook, sheet, XLSX_FONT_SIZE_HEADING,
                                 True, XLSX_GRAY_200, align, 2, 2)
                cursor_x = cursor_x + 1

            # Set cursor coordinates for the table generation
            cursor_y += 1
            cursor_x = 0
            for line in journal_vals['lines'][:-1]:
                is_first_aml_line = False
                for column in columns:
                    border_top = 0 if not is_first_aml_line else 1
                    align = 'left'

                    if line.get(column['label'], {}).get('data'):
                        data = line[column['label']]['data']
                        is_date = isinstance(data, datetime.date)
                        bold = False

                        if 'o_right_alignment' in column.get('class', ''):
                            align = 'right'

                        if line[column['label']].get('class') and 'o_bold' in line[column['label']]['class']:
                            # if the cell has bold styling, should only be on the first line of each aml
                            is_first_aml_line = True
                            border_top = 1
                            bold = True

                        # จุดแทรก: ช่องเงินเขียนเป็นตัวเลข + num_format พ่วงสกุลเงิน แทนข้อความ
                        parsed = _parse_money(data) if column['label'] in money_labels else None
                        if parsed is not None:
                            style = self._azs_money_format(workbook, money_format_cache, parsed[1], bold, 'white', border_top, 0, XLSX_BORDER_COLOR)
                            report._set_xlsx_cell_sizes(sheet, fonts[XLSX_FONT_SIZE_DEFAULT], cursor_x, cursor_y, data, style, False)
                            sheet.write_number(cursor_y, cursor_x, parsed[0], style)
                        else:
                            self._write_cell(cursor_x, cursor_y, data, 1, is_date, report, fonts, workbook, sheet, XLSX_FONT_SIZE_DEFAULT,
                                             bold, 'white', align, 0, border_top, XLSX_BORDER_COLOR)

                    else:
                        # Empty value
                        self._write_cell(cursor_x, cursor_y, '', 1, False, report, fonts, workbook, sheet, XLSX_FONT_SIZE_DEFAULT, False,
                                         'white', align, 0, border_top, XLSX_BORDER_COLOR)

                    cursor_x += 1
                cursor_x = 0
                cursor_y += 1

            # Draw total line
            # จุดแทรก: ช่องยอดรวมที่เป็นตัวเลขและตรงกับผลบวกของแถวข้อมูล เขียนเป็นสูตร =SUM
            total_line = journal_vals['lines'][-1]
            data_lines = journal_vals['lines'][:-1]
            for column in columns:
                data = ''
                align = 'left'

                if total_line.get(column['label'], {}).get('data'):
                    data = total_line[column['label']]['data']

                if 'o_right_alignment' in column.get('class', ''):
                    align = 'right'

                parsed_total = _parse_money(data) if column['label'] in money_labels else None
                if parsed_total is not None and data_lines:
                    expected = sum(
                        parsed[0] for line in data_lines
                        if (parsed := _parse_money(line.get(column['label'], {}).get('data'))) is not None
                    )
                    style = self._azs_money_format(workbook, money_format_cache, parsed_total[1], True, XLSX_GRAY_200, 2, 2, '0x000000')
                    report._set_xlsx_cell_sizes(sheet, fonts[XLSX_FONT_SIZE_DEFAULT], cursor_x, cursor_y, data, style, False)
                    if abs(parsed_total[0] - expected) <= 0.02:
                        letter = _col_letter(cursor_x)
                        # แถวข้อมูลอยู่ Excel-row 2 ถึง cursor_y (1-based), แถว Total คือ cursor_y + 1
                        sheet.write_formula(cursor_y, cursor_x, f"=SUM({letter}2:{letter}{cursor_y})", style, parsed_total[0])
                    else:
                        sheet.write_number(cursor_y, cursor_x, parsed_total[0], style)
                else:
                    self._write_cell(cursor_x, cursor_y, data, 1, False, report, fonts, workbook, sheet, XLSX_FONT_SIZE_DEFAULT, True,
                                     XLSX_GRAY_200, align, 2, 2)
                cursor_x += 1

            cursor_x = 0

            sheet.set_default_row(20)
            sheet.set_row(0, 30)

            # Tax tables drawing
            if journal_vals.get('tax_summary'):
                self._write_tax_summaries_to_sheet(report, workbook, sheet, fonts, len(columns) + 1, 1, journal_vals['tax_summary'])

        if document_data.get('global_tax_summary'):
            self._write_tax_summaries_to_sheet(
                report,
                workbook,
                workbook.add_worksheet(_('Global Tax Summary')[:31]),
                fonts,
                0,
                0,
                document_data['global_tax_summary']
            )

        report._add_options_xlsx_sheet(workbook, [print_options])
        workbook.close()
        output.seek(0)
        generated_file = output.read()
        output.close()

        return {
            'file_name': report.get_default_report_filename(options, 'xlsx'),
            'file_content': generated_file,
            'file_type': 'xlsx',
        }
