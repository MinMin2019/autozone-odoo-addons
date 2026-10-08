# -*- coding: utf-8 -*-
"""Export Excel 4 ชีต — เลย์เอาต์ตาม other/Autozone-แบบฟอร์มตรวจนับสต๊อก-BHA-v3.xlsx

1. ใบตรวจนับ   : พิมพ์ให้สาขานับ (Plant, Material, Description, Quantity, UOM, Amount,
                 นับครั้งที่ 1, นับครั้งที่ 2, ยืนยันจำนวน, ผลต่าง, หมายเหตุ) + คอลัมน์ L = product id (เทา)
                 blind → Quantity/Amount/ผลต่าง เว้นว่าง
2. กระทบยอด    : ณ วันตัดยอด / +รับ / -จ่าย (Odoo กรอกให้) / ควรมี / นับได้ (สูตรดึงจากชีต 1) /
                 ผลต่าง จำนวน-%-มูลค่า / สถานะ + สรุปท้ายตาราง — ทั้งหมดเป็นสูตร Excel จึงใช้ต่อได้เอง
3. หมายเหตุผลต่าง : สูตรอ้างชีต 2 + ช่องเหลือง สาเหตุ/เอกสาร/ผู้รับผิดชอบ/การแก้ไข/วันที่แล้วเสร็จ + ลายเซ็น
4. วิธีใช้      : คำอธิบาย (วันที่/คลังเปลี่ยนตามใบ)

ไฟล์ที่กรอกแล้วอัปโหลดกลับได้ที่ปุ่ม "นำเข้าจาก Excel" (อ่านชีต 1 คอลัมน์นับ + ชีต 3 คอลัมน์สาเหตุ)
"""
import base64
import io
import re

from odoo import fields, models

FONT = "Leelawadee UI"
SHEET_COUNT = "ใบตรวจนับ"
SHEET_RECON = "กระทบยอด"
SHEET_NOTES = "หมายเหตุผลต่าง"
SHEET_HELP = "วิธีใช้"


class StockCount(models.Model):
    _inherit = "az.stock.count"

    def action_export_xlsx(self):
        if not self:
            return False
        data = self._build_count_xlsx()
        if len(self) == 1:
            base = "%s-แบบฟอร์มตรวจนับสต๊อก-%s" % (self.name, self.warehouse_id.code or self.warehouse_id.name)
        else:
            base = "StockCount_%s" % fields.Date.context_today(self).strftime("%Y%m%d")
        attachment = self.env["ir.attachment"].create({
            "name": "%s.xlsx" % re.sub(r"[\\/:*?\"<>|]+", "_", base),
            "type": "binary",
            "datas": base64.b64encode(data),
            "res_model": self._name if len(self) == 1 else False,
            "res_id": self.id if len(self) == 1 else False,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%d?download=true" % attachment.id,
            "target": "self",
        }

    def _xlsx_formats(self, wb):
        base = {"font_name": FONT, "font_size": 9}
        box = dict(base, border=1)
        return {
            "title": wb.add_format(dict(base, font_size=12, bold=True)),
            "title13": wb.add_format(dict(base, font_size=13, bold=True)),
            "sub": wb.add_format(dict(base, font_size=11, bold=True)),
            "bold": wb.add_format(dict(base, bold=True)),
            "plain": wb.add_format(base),
            "wrap": wb.add_format(dict(base, text_wrap=True, valign="top")),
            "lbl": wb.add_format(dict(base, bold=True, bg_color="#FFFF80")),
            "val": wb.add_format(dict(base, bg_color="#FFFF80")),
            "grp_hdr": wb.add_format(dict(base, bold=True, align="center")),
            "head": wb.add_format(dict(box, bold=True, bg_color="#DCE6F1", align="center",
                                       valign="vcenter", text_wrap=True)),
            "head_nb": wb.add_format(dict(base, bold=True, bg_color="#DCE6F1", align="center",
                                          valign="vcenter", text_wrap=True)),
            "group": wb.add_format(dict(box, bold=True, bg_color="#BDE1F2", align="left")),
            "text": wb.add_format(box),
            "text_nb": wb.add_format(base),
            "int": wb.add_format(dict(box, align="center")),
            "int_nb": wb.add_format(dict(base, align="center")),
            "num": wb.add_format(dict(box, num_format="#,##0.00")),
            "num_nb": wb.add_format(dict(base, num_format="#,##0.00")),
            "pct": wb.add_format(dict(box, num_format="0.00%")),
            "pct_nb": wb.add_format(dict(base, num_format="0.00%")),
            "num_y": wb.add_format(dict(box, num_format="#,##0.00", bg_color="#FFFF80")),
            "text_y": wb.add_format(dict(box, bg_color="#FFFF80")),
            "text_y_nb": wb.add_format(dict(base, bg_color="#FFFF80")),
            "date_y_nb": wb.add_format(dict(base, bg_color="#FFFF80", num_format="dd/mm/yyyy")),
            "tot_l": wb.add_format(dict(box, bold=True, bg_color="#FCE4D6")),
            "tot_n": wb.add_format(dict(box, bold=True, bg_color="#FCE4D6", num_format="#,##0.00")),
            "sum_l": wb.add_format(dict(base, bg_color="#FFFF80")),
            "sum_lb": wb.add_format(dict(base, bold=True, bg_color="#FFFF80")),
            "sum_i": wb.add_format(dict(base, bg_color="#FFFF80", num_format="#,##0")),
            "sum_n": wb.add_format(dict(base, bg_color="#FFFF80", num_format="#,##0.00")),
            "id": wb.add_format(dict(base, font_size=8, font_color="#A6A6A6")),
            "id_head": wb.add_format(dict(base, font_size=8, font_color="#A6A6A6", align="center")),
        }

    def _build_count_xlsx(self):
        import xlsxwriter

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        fmt = self._xlsx_formats(wb)
        multi = len(self) > 1
        for rec in self:
            suffix = (" " + rec.name) if multi else ""
            names = {k: (v + suffix)[:31] for k, v in (
                ("count", SHEET_COUNT), ("recon", SHEET_RECON), ("notes", SHEET_NOTES), ("help", SHEET_HELP))}
            ws_count = wb.add_worksheet(names["count"])
            ws_recon = wb.add_worksheet(names["recon"])
            ws_notes = wb.add_worksheet(names["notes"])
            ws_help = wb.add_worksheet(names["help"])
            lines = rec.line_ids.sorted(lambda l: (l.sequence, l.id))
            row_map = rec._write_sheet_count(ws_count, fmt, lines)
            recon_rows = rec._write_sheet_recon(ws_recon, fmt, lines, row_map, names["count"])
            rec._write_sheet_notes(ws_notes, fmt, lines, recon_rows, names["recon"])
            rec._write_sheet_help(ws_help, fmt)
        wb.close()
        return buf.getvalue()

    # ------------------------------------------------------------------
    # ชีต 1 ใบตรวจนับ
    # ------------------------------------------------------------------
    def _wh_label(self):
        self.ensure_one()
        wh = self.warehouse_id
        label = wh.code or wh.name or ""
        if self.location_id and self.location_id != wh.lot_stock_id:
            label += " (%s)" % self.location_id.complete_name
        return label

    def _write_sheet_count(self, ws, fmt, lines):
        """คืน {line.id: row index (0-based) ในชีตนี้} ให้ชีตกระทบยอดอ้างสูตร"""
        self.ensure_one()
        show_sys = self._show_system_qty()
        show_cnt = self._show_counted()
        d_cut, d_cnt = self._fmt_date(self.date_cutoff), self._fmt_date(self.date_count)
        underscores = "_" * 25

        for c, w in enumerate([7.8, 22.8, 46.8, 11.8, 9.8, 13.8, 11.8, 11.8, 12.8, 11.8, 24.8]):
            ws.set_column(c, c, w)
        ws.set_column(11, 11, 7, fmt["id"])

        ws.set_row(0, 19)
        ws.write(0, 0, self.company_id.name or "", fmt["title"])
        ws.set_row(1, 17)
        ws.write(1, 0, "รายละเอียดสินค้าคงคลัง  ใบตรวจนับ  สาขา %s" % self._wh_label(), fmt["sub"])
        ws.write(2, 0, "ยอดตามบัญชี ณ วันที่ %s   ตรวจนับจริงวันที่ %s" % (d_cut, d_cnt), fmt["bold"])
        ws.write(3, 0, "เลขที่ใบนับ", fmt["lbl"])
        ws.write(3, 1, "", fmt["lbl"])
        ws.write(3, 2, self.name or "", fmt["val"])
        ws.write(3, 5, "รอบการนับ", fmt["lbl"])
        ws.write(3, 6, self._count_type_label(), fmt["val"])
        ws.write(4, 0, "ผู้นับคนที่ 1", fmt["lbl"])
        ws.write(4, 1, "", fmt["lbl"])
        ws.write(4, 2, self.counter1 or underscores, fmt["val"])
        ws.write(4, 5, "ผู้นับคนที่ 2", fmt["lbl"])
        ws.write(4, 6, self.counter2 or underscores, fmt["val"])
        if show_sys:
            note = ("ผู้นับสองคนนับแยกกัน เขียนช่อง นับครั้งที่ 1 / 2  ไม่ตรงให้นับครั้งที่สามต่อหน้าหัวหน้าคลัง "
                    "แล้วเขียนตัวเลขที่ยืนยันแล้วในช่อง ยืนยันจำนวน  ช่อง ผลต่าง คือผลต่างเบื้องต้นเทียบกับบัญชี ณ %s  "
                    "การกระทบยอดจริงที่รวมรับเข้า/จ่ายออกช่วง %s อยู่ในชีต %s") % (
                d_cut, self._period_label() or d_cnt, SHEET_RECON)
        else:
            note = ("ผู้นับสองคนนับแยกกัน เขียนช่อง นับครั้งที่ 1 / 2  ไม่ตรงให้นับครั้งที่สามต่อหน้าหัวหน้าคลัง "
                    "แล้วเขียนตัวเลขที่ยืนยันแล้วในช่อง ยืนยันจำนวน  ยอดตามบัญชีไม่แสดงในใบนี้ (นับของจริงก่อน) "
                    "การกระทบยอดอยู่ในชีต %s") % SHEET_RECON
        ws.write(6, 0, note, fmt["plain"])

        ws.merge_range(7, 3, 7, 5, "ยอดตามบัญชี ณ %s" % d_cut, fmt["grp_hdr"])
        ws.merge_range(7, 6, 7, 10, "บันทึกจากการนับจริง ณ %s" % d_cnt, fmt["grp_hdr"])
        head_row = 8
        heads = ["Plant", "Material", "Description", "Quantity", "UOM", "Amount",
                 "นับครั้งที่ 1", "นับครั้งที่ 2", "ยืนยันจำนวน", "ผลต่าง", "หมายเหตุ"]
        for c, h in enumerate(heads):
            ws.write(head_row, c, h, fmt["head"])
        ws.write(head_row, 11, "ID", fmt["id_head"])
        ws.set_row(head_row, 32)

        plant = self.warehouse_id.code or self.warehouse_id.name or ""
        row = head_row + 1
        first_data = row
        row_map = {}
        for categ, grp_lines in self._report_groups(lines):
            ws.merge_range(row, 0, row, 10, categ, fmt["group"])
            row += 1
            for line in grp_lines:
                r1 = row + 1  # เลขแถว Excel
                row_map[line.id] = row
                ws.write(row, 0, plant, fmt["text"])
                ws.write(row, 1, line.product_id.default_code or "", fmt["text"])
                ws.write(row, 2, line.product_id.name or "", fmt["text"])
                if show_sys:
                    ws.write_number(row, 3, line.qty_system, fmt["num"])
                else:
                    ws.write_blank(row, 3, None, fmt["num"])
                ws.write(row, 4, line.uom_id.name or "", fmt["text"])
                if show_sys:
                    ws.write_number(row, 5, line.amount, fmt["num"])
                else:
                    ws.write_blank(row, 5, None, fmt["num"])
                for c, val in ((6, line.qty_count1), (7, line.qty_count2)):
                    if show_cnt and val:
                        ws.write_number(row, c, val, fmt["num_y"])
                    else:
                        ws.write_blank(row, c, None, fmt["num_y"])
                if show_cnt and line.counted:
                    ws.write_number(row, 8, line.qty_counted, fmt["num_y"])
                else:
                    ws.write_blank(row, 8, None, fmt["num_y"])
                if show_sys:
                    ws.write_formula(row, 9, '=IF(I%d="","",I%d-D%d)' % (r1, r1, r1), fmt["num_y"])
                else:
                    ws.write_blank(row, 9, None, fmt["num_y"])
                ws.write(row, 10, line.note or "", fmt["text_y"])
                ws.write_number(row, 11, line.product_id.id, fmt["id"])
                row += 1
        last_data = row - 1

        ws.write(row, 0, "", fmt["tot_l"])
        ws.write(row, 1, "", fmt["tot_l"])
        ws.write(row, 2, "รวมทั้งสิ้น", fmt["tot_l"])
        for c, col in ((3, "D"), (5, "F"), (8, "I"), (9, "J")):
            if col in ("D", "F", "J") and not show_sys:
                ws.write(row, c, "", fmt["tot_l"])
            else:
                ws.write_formula(row, c, "=SUM(%s%d:%s%d)" % (col, first_data + 1, col, last_data + 1), fmt["tot_n"])
        for c in (4, 6, 7, 10):
            ws.write(row, c, "", fmt["tot_l"])

        row += 3
        for c, label in ((0, "ผู้นับคนที่ 1"), (2, "ผู้นับคนที่ 2"), (5, "ผู้ทาน / หัวหน้าคลัง"), (8, "ผู้อนุมัติ")):
            ws.write(row, c, label, fmt["bold"])
            ws.write(row + 2, c, "ลงชื่อ ______________", fmt["plain"])
            ws.write(row + 3, c, "วันที่ ______________", fmt["plain"])

        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.repeat_rows(7, 8)
        ws.set_margins(left=0.31, right=0.31, top=0.39, bottom=0.39)
        ws.set_footer("&C&\"%s\"หน้า &P / &N" % FONT)
        ws.freeze_panes(head_row + 1, 0)
        return row_map

    # ------------------------------------------------------------------
    # ชีต 2 กระทบยอด
    # ------------------------------------------------------------------
    def _write_sheet_recon(self, ws, fmt, lines, row_map, count_sheet):
        """คืน {line.id: row index ในชีตนี้}"""
        self.ensure_one()
        d_cut, d_cnt = self._fmt_date(self.date_cutoff), self._fmt_date(self.date_count)
        q = "'%s'!" % count_sheet.replace("'", "''")
        for c, w in enumerate([7.8, 22.8, 44.8, 8.8, 13.8, 11.8, 11.8, 13.8, 13.8, 11.8, 9.8, 12.8, 13.8, 11.8]):
            ws.set_column(c, c, w)

        ws.write(0, 0, self.company_id.name or "", fmt["title"])
        ws.write(1, 0, "รายละเอียดการตรวจนับสินค้าคงคลัง  สาขา %s" % self._wh_label(), fmt["sub"])
        ws.write(2, 0, "สิ้นสุด ณ วันที่ %s   ตรวจนับจริงวันที่ %s" % (d_cut, d_cnt), fmt["bold"])
        period = self._period_label()
        if period:
            ws.write(3, 0, "ช่อง บวกรับ / หักจ่าย ดึงจาก Odoo ให้แล้ว = ความเคลื่อนไหวของคลัง %s ช่วง %s "
                           "(คำนวณเมื่อ %s)  ช่อง ตรวจนับได้ ดึงจากชีต %s อัตโนมัติ" % (
                               self.location_id.complete_name, period, self._snapshot_local(), count_sheet),
                     fmt["plain"])
        else:
            ws.write(3, 0, "นับวันเดียวกับวันตัดยอด จึงไม่มีรับเข้า/จ่ายออกคั่น  ช่อง ตรวจนับได้ ดึงจากชีต %s อัตโนมัติ"
                     % count_sheet, fmt["plain"])

        ws.write(4, 4, "ปริมาณคงเหลือตามบัญชี", fmt["grp_hdr"])
        ws.merge_range(4, 5, 4, 6, "ธุรกรรมระหว่าง %s ถึง %s" % (d_cut, d_cnt), fmt["grp_hdr"])
        ws.merge_range(4, 9, 4, 10, "ผลต่าง", fmt["grp_hdr"])
        head_row = 5
        heads = ["Plant", "Material", "Description", "UOM", "ณ %s" % d_cut, "+ บวกรับ", "- หักจ่าย",
                 "ยอดที่ควรมี ณ %s" % d_cnt, "ตรวจนับได้ ณ %s" % d_cnt, "จำนวน", "%", "ราคาทุน/หน่วย",
                 "ผลต่างมูลค่า", "สถานะ"]
        for c, h in enumerate(heads):
            ws.write(head_row, c, h, fmt["head"])
        ws.set_row(head_row, 32)

        plant = self.warehouse_id.code or self.warehouse_id.name or ""
        row = head_row + 1
        first = row
        recon_rows = {}
        for line in lines:
            r = row + 1
            cr = row_map[line.id] + 1
            recon_rows[line.id] = row
            ws.write(row, 0, plant, fmt["text"])
            ws.write(row, 1, line.product_id.default_code or "", fmt["text"])
            ws.write(row, 2, line.product_id.name or "", fmt["text"])
            ws.write(row, 3, line.uom_id.name or "", fmt["text"])
            ws.write_number(row, 4, line.qty_system, fmt["num"])
            ws.write_number(row, 5, line.qty_in, fmt["num"])
            ws.write_number(row, 6, line.qty_out, fmt["num"])
            ws.write_formula(row, 7, "=E%d+N(F%d)-N(G%d)" % (r, r, r), fmt["num"])
            ws.write_formula(row, 8, '=IF(%sI%d="","",%sI%d)' % (q, cr, q, cr), fmt["num"])
            ws.write_formula(row, 9, '=IF(I%d="","",I%d-H%d)' % (r, r, r), fmt["num"])
            ws.write_formula(row, 10, '=IF(OR(I%d="",H%d=0),"",J%d/H%d)' % (r, r, r, r), fmt["pct"])
            ws.write_number(row, 11, line.standard_price, fmt["num"])
            ws.write_formula(row, 12, '=IF(J%d="","",J%d*L%d)' % (r, r, r), fmt["num"])
            ws.write_formula(row, 13, '=IF(I%d="","ยังไม่ได้นับ",IF(J%d=0,"ตรง",IF(J%d>0,"เกิน","ขาด")))' % (r, r, r),
                             fmt["text"])
            row += 1
        last = row - 1
        if last >= first:
            ws.autofilter(head_row, 0, last, 13)
        rng = lambda col: "%s%d:%s%d" % (col, first + 1, col, last + 1)

        row += 2
        ws.write(row, 0, "สรุปผลการตรวจนับ", fmt["sum_lb"])
        ws.write(row, 1, "", fmt["sum_lb"])
        ws.write(row, 2, "", fmt["sum_lb"])
        summary = [
            ("จำนวนรายการที่ต้องนับ", "=COUNTA(%s)" % rng("B"), "sum_i"),
            ("นับแล้ว", '=COUNTIF(%s,"<>ยังไม่ได้นับ")' % rng("N"), "sum_i"),
            ("ยังไม่ได้นับ", '=COUNTIF(%s,"ยังไม่ได้นับ")' % rng("N"), "sum_i"),
            ("ตรงกับบัญชี", '=COUNTIF(%s,"ตรง")' % rng("N"), "sum_i"),
            ("ขาด", '=COUNTIF(%s,"ขาด")' % rng("N"), "sum_i"),
            ("เกิน", '=COUNTIF(%s,"เกิน")' % rng("N"), "sum_i"),
            ("มูลค่าส่วนที่ขาด", '=SUMIF(%s,"ขาด",%s)' % (rng("N"), rng("M")), "sum_n"),
            ("มูลค่าส่วนที่เกิน", '=SUMIF(%s,"เกิน",%s)' % (rng("N"), rng("M")), "sum_n"),
            ("ผลต่างมูลค่าสุทธิ", "=SUM(%s)" % rng("M"), "sum_n"),
            ("มูลค่าสต๊อกตามบัญชี", "=SUMPRODUCT(%s,%s)" % (rng("E"), rng("L")), "sum_n"),
        ]
        for label, formula, f in summary:
            row += 1
            ws.write(row, 0, label, fmt["sum_l"])
            ws.write(row, 1, "", fmt["sum_l"])
            ws.write_formula(row, 2, formula, fmt[f])

        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.repeat_rows(4, 5)
        ws.set_footer("&C&\"%s\"หน้า &P / &N" % FONT)
        ws.freeze_panes(head_row + 1, 0)
        return recon_rows

    # ------------------------------------------------------------------
    # ชีต 3 หมายเหตุผลต่าง
    # ------------------------------------------------------------------
    def _write_sheet_notes(self, ws, fmt, lines, recon_rows, recon_sheet):
        self.ensure_one()
        q = "'%s'!" % recon_sheet.replace("'", "''")
        for c, w in enumerate([6.8, 22.8, 44.8, 8.8, 12.8, 9.8, 9.8, 11.8, 11.8, 11.8, 9.8, 11.8, 11.8,
                               40.8, 30.8, 18.8, 40.8, 15.8]):
            ws.set_column(c, c, w)
        ws.write(0, 0, "บันทึกหมายเหตุผลต่างจากการตรวจนับ  สาขา %s" % self._wh_label(), fmt["title13"])
        ws.write(1, 0, "ไม่มีการปรับยอดในระบบ  ทุกผลต่างให้บันทึกสาเหตุไว้เป็นหลักฐาน แล้วแก้ที่ต้นทางด้วยเอกสารที่ถูกต้อง",
                 fmt["plain"])
        ws.write(2, 0, "กรองคอลัมน์ สถานะ ให้เหลือเฉพาะ ขาด และ เกิน เพื่อดูเฉพาะรายการที่ต้องอธิบาย  "
                       "ช่องสีเหลืองกรอกเอง (หรือกรอกในจอ Odoo แท็บ กระทบยอด / สาเหตุผลต่าง แล้ว Export ใหม่)",
                 fmt["plain"])
        head_row = 4
        heads = ["ลำดับ", "Material", "Description", "UOM", "ตามบัญชี ณ %s" % self._fmt_date(self.date_cutoff),
                 "+ บวกรับ", "- หักจ่าย", "ยอดที่ควรมี", "ตรวจนับได้", "ผลต่างจำนวน", "ผลต่าง %", "ผลต่างมูลค่า",
                 "สถานะ", "สาเหตุของผลต่าง", "เอกสาร / หลักฐานอ้างอิง", "ผู้รับผิดชอบ",
                 "การดำเนินการแก้ไขที่ต้นทาง", "วันที่แล้วเสร็จ"]
        for c, h in enumerate(heads):
            ws.write(head_row, c, h, fmt["head_nb"])
        ws.set_row(head_row, 32)
        row = head_row + 1
        first = row
        for seq, line in enumerate(lines, 1):
            rr = recon_rows[line.id] + 1
            ws.write_number(row, 0, seq, fmt["int_nb"])
            ws.write(row, 1, line.product_id.default_code or "", fmt["text_nb"])
            ws.write(row, 2, line.product_id.name or "", fmt["text_nb"])
            ws.write(row, 3, line.uom_id.name or "", fmt["text_nb"])
            for c, col in ((4, "E"), (5, "F"), (6, "G"), (7, "H"), (8, "I"), (9, "J")):
                ws.write_formula(row, c, "=%s%s%d" % (q, col, rr), fmt["num_nb"])
            ws.write_formula(row, 10, "=%sK%d" % (q, rr), fmt["pct_nb"])
            ws.write_formula(row, 11, "=%sM%d" % (q, rr), fmt["num_nb"])
            ws.write_formula(row, 12, "=%sN%d" % (q, rr), fmt["text_nb"])
            ws.write(row, 13, line.reason or "", fmt["text_y_nb"])
            ws.write(row, 14, line.ref_doc or "", fmt["text_y_nb"])
            ws.write(row, 15, line.responsible or "", fmt["text_y_nb"])
            ws.write(row, 16, line.action_taken or "", fmt["text_y_nb"])
            if line.date_resolved:
                ws.write_datetime(row, 17, fields.Datetime.to_datetime(line.date_resolved), fmt["date_y_nb"])
            else:
                ws.write_blank(row, 17, None, fmt["date_y_nb"])
            row += 1
        if row > first:
            ws.autofilter(head_row, 0, row - 1, 17)
        row += 2
        for c, label in ((0, "ผู้สรุปผลต่าง"), (4, "หัวหน้าคลัง"), (8, "ฝ่ายบัญชี"), (13, "ผู้อนุมัติ")):
            ws.write(row, c, label, fmt["bold"])
            ws.write(row + 2, c, "ลงชื่อ ______________", fmt["plain"])
            ws.write(row + 3, c, "วันที่ ______________", fmt["plain"])
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.repeat_rows(head_row)
        ws.freeze_panes(head_row + 1, 0)

    # ------------------------------------------------------------------
    # ชีต 4 วิธีใช้
    # ------------------------------------------------------------------
    def _write_sheet_help(self, ws, fmt):
        self.ensure_one()
        d_cut, d_cnt = self._fmt_date(self.date_cutoff), self._fmt_date(self.date_count)
        period = self._period_label() or d_cnt
        loc = self.location_id.complete_name
        wh = self._wh_label()
        ws.set_column(0, 0, 125)
        text = [
            ("วิธีใช้แบบฟอร์มตรวจนับสต๊อก", "title13"),
            ("", None),
            ("หลักการของแบบฟอร์มชุดนี้", "bold"),
            ("ตรวจนับเพื่อตรวจสอบและหาสาเหตุ  ไม่ใช่เพื่อปรับยอดในระบบให้ตรงกับของจริง  เมื่อพบผลต่างให้บันทึกหมายเหตุไว้ "
             "แล้วแก้ที่ต้นทางด้วยเอกสารที่ถูกต้อง  (ถ้าจำเป็นต้องปรับยอดจริง ๆ Inventory Manager กดปรับปรุงสต็อกจากใบนับใน Odoo ได้ "
             "ซึ่งจะบันทึกไว้เป็นหลักฐานว่าปรับจากใบนับใบไหน)", "wrap"),
            ("", None),
            ("นับวันหนึ่ง แต่ยอดบัญชีตัดอีกวันหนึ่ง ทำอย่างไร", "bold"),
            ("ยอดตามบัญชีในไฟล์นี้คือยอด ณ %s  แต่ไปนับของจริงวันที่ %s  ระหว่างสองวันนี้มีของรับเข้าและจ่ายออก "
             "จึงต้องเดินยอดไปข้างหน้าก่อนแล้วค่อยเทียบ" % (d_cut, d_cnt), "wrap"),
            ("สูตรที่ใช้   ยอดที่ควรมี ณ %s  =  ยอดตามบัญชี ณ %s  บวก  รับเข้า %s  ลบ  จ่ายออก %s"
             % (d_cnt, d_cut, period, period), "wrap"),
            ("ผลต่าง  =  ตรวจนับได้  ลบ  ยอดที่ควรมี     ติดลบคือของขาด  เป็นบวกคือของเกิน", "plain"),
            ("ผลต่าง %  =  ผลต่างจำนวน  หารด้วย  ยอดที่ควรมี     ใช้ดูว่าผลต่างนั้นใหญ่หรือเล็กเมื่อเทียบกับปริมาณที่ถือครอง", "plain"),
            ("", None),
            ("ขั้นตอนทำงาน", "bold"),
            ("1  พิมพ์ชีต %s  ตั้งค่าหน้าไว้แล้วเป็น A4 แนวนอน พอดีความกว้าง ซ้ำหัวตารางทุกหน้า  (หรือกดพิมพ์ PDF จาก Odoo)" % SHEET_COUNT, "plain"),
            ("2  ให้ผู้นับสองคนนับแยกกัน เขียนลงช่อง นับครั้งที่ 1 และ นับครั้งที่ 2  ถ้าไม่ตรงให้นับครั้งที่สามต่อหน้าหัวหน้าคลัง", "plain"),
            ("3  เขียนตัวเลขที่ยืนยันแล้วในช่อง ยืนยันจำนวน  แล้วคีย์กลับเข้าไฟล์นี้ในชีต %s ช่องเดียวเท่านั้น  ชีตอื่นดึงไปให้เอง" % SHEET_COUNT, "plain"),
            ("   หรือคีย์ในจอ Odoo (ใบตรวจนับ %s แท็บ รายการนับ) หรืออัปโหลดไฟล์นี้กลับเข้า Odoo ด้วยปุ่ม นำเข้าจาก Excel" % self.name, "plain"),
            ("4  ช่อง บวกรับ และ หักจ่าย ในชีต %s Odoo กรอกให้แล้ว จากประวัติการเคลื่อนไหวของคลัง %s ช่วง %s" % (SHEET_RECON, loc, period), "plain"),
            ("   ถ้ามีการบันทึกเอกสารย้อนหลังเพิ่มหลังจาก Export ไฟล์นี้ ให้กด รีเฟรชยอดระบบ ใน Odoo แล้ว Export ใหม่", "plain"),
            ("5  ชีต %s จะคำนวณ ยอดที่ควรมี ผลต่างจำนวน ผลต่าง %% ผลต่างมูลค่า และสถานะให้เอง  พร้อมสรุปยอดรวมท้ายตาราง" % SHEET_RECON, "plain"),
            ("6  เปิดชีต %s  กรองสถานะให้เหลือเฉพาะ ขาด และ เกิน  แล้วกรอกช่องสีเหลืองให้ครบทุกรายการ" % SHEET_NOTES, "plain"),
            ("7  ให้ผู้สรุป หัวหน้าคลัง ฝ่ายบัญชี และผู้อนุมัติ ลงนามท้ายชีต แล้วเก็บไว้เป็นหลักฐาน", "plain"),
            ("", None),
            ("ทำไมใบตรวจนับจึงไม่แสดงยอดในระบบ", "bold"),
            ("ถ้าผู้นับเห็นตัวเลขไว้ก่อน จะเกิดการนับให้ตรงกับที่เห็นแทนที่จะนับของจริง  ผลต่างที่ควรเจอจะหายไปหมด  "
             "ยอดตามบัญชีจึงไปแสดงเฉพาะในชีต %s" % SHEET_RECON, "wrap"),
            ("", None),
            ("สาเหตุของผลต่างที่พบบ่อย  ใช้เป็นแนวทางกรอกช่องสาเหตุ", "bold"),
            ("เอกสารยังไม่ได้บันทึกในระบบ  เช่น ใบโอนเข้าสาขาหรือใบเบิกใช้วัสดุที่ยังค้าง  แก้ด้วยการบันทึกเอกสารให้ครบ", "plain"),
            ("บันทึกผิดสินค้า  เบิกตัวหนึ่งแต่คีย์อีกตัวหนึ่ง  มักพบเป็นคู่ คือตัวหนึ่งขาดอีกตัวหนึ่งเกินจำนวนเท่ากัน", "plain"),
            ("บันทึกผิดหน่วย  เช่น ลัง กับ ม้วน  ผลต่างจะเป็นจำนวนเท่าของกันและกัน", "plain"),
            ("ของเสียหายหรือหมดอายุแต่ยังไม่ได้ตัดออก", "plain"),
            ("รับของมาแล้วแต่ยังไม่ได้คีย์ใบรับ", "plain"),
            ("นับผิดหรือนับตก  ตรวจซ้ำก่อนสรุปว่าเป็นผลต่างจริง", "plain"),
            ("เอกสารบันทึกย้อนหลังหลัง Export  ถ้าผลต่างของสินค้าตัวใดเท่ากับจำนวนที่รับหรือเบิกพอดี ให้รีเฟรชยอดระบบใน Odoo ก่อน", "plain"),
            ("", None),
            ("การควบคุมที่ควรมี", "bold"),
            ("ผู้นับต้องไม่ใช่คนเดียวกับผู้ดูแลคลังประจำวัน  อย่างน้อยหนึ่งในสองคนควรมาจากหน่วยงานอื่น", "plain"),
            ("ผลต่างทุกรายการต้องมีคำอธิบาย  ห้ามปล่อยช่องสาเหตุว่าง  (Odoo ไม่ให้ปิดใบถ้ายังมีรายการขาด/เกินที่ไม่มีสาเหตุ)", "plain"),
            ("เก็บใบตรวจนับที่ลงนามแล้วคู่กับชีตหมายเหตุผลต่าง เป็นหลักฐานประกอบการตรวจสอบ", "plain"),
            ("", None),
            ("หมายเหตุเรื่องข้อมูลในไฟล์นี้", "bold"),
            ("ยอดตามบัญชีในไฟล์นี้คือยอดคงเหลือของคลัง %s ณ สิ้นวัน %s คำนวณจาก Odoo เมื่อ %s" % (loc, d_cut, self._snapshot_local()), "plain"),
            ("สินค้าที่ยอดเป็นศูนย์ในระบบไม่ได้อยู่ในใบนับ (เว้นแต่ติ๊ก รวมสินค้าที่ยอดเป็น 0)  ถ้าพบของจริงที่ไม่มีในรายการ ให้เขียนเพิ่มท้ายใบแล้วแจ้งบัญชี", "plain"),
            ("ไฟล์นี้ทำไว้สำหรับสาขา %s ใบตรวจนับ %s  สาขาอื่นให้สร้างใบนับแยกเพราะรายการสินค้าไม่เหมือนกัน" % (wh, self.name), "plain"),
            ("คอลัมน์ ID (ตัวเทา) ท้ายชีต %s ใช้ตอนนำเข้ากลับ Odoo  ห้ามลบ" % SHEET_COUNT, "plain"),
        ]
        for r, (line, f) in enumerate(text):
            if f:
                ws.write(r, 0, line, fmt[f])
