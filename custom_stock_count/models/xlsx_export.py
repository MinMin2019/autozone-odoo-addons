# -*- coding: utf-8 -*-
"""Export Excel แบบฟอร์มตรวจนับ — เลย์เอาต์ตามไฟล์ other/Autozone-แบบฟอร์มตรวจนับสต๊อก-BHA.xlsx

* คอลัมน์ A-H ตามแบบ (ลำดับ รหัส ชื่อ หน่วย ยอดคงเหลือ ยอดตรวจนับ ผลต่าง หมายเหตุ)
* คอลัมน์ I = product id (ตัวอักษรเทาเล็ก) ให้ตัวนำเข้า Excel จับคู่สินค้าได้แม่นแม้รหัสซ้ำ/ชื่อเปลี่ยน
* หัวหมวด 1 แถว merge A:H ก่อนรายการของหมวดนั้น (เหมือนแบบฟอร์มกระดาษ)
* ยอดคงเหลือ: เว้นว่างเมื่อ blind และยังนับไม่เสร็จ; ยอดนับ/ผลต่าง: ใส่เฉพาะรายการที่นับแล้ว
* แนวนอน fit 1 หน้ากว้าง, พิมพ์หัวตารางซ้ำทุกหน้า, ท้ายกระดาษ "หน้า x / y"
"""
import base64
import io
import re

from odoo import fields, models

FONT = "Leelawadee UI"


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

    def _build_count_xlsx(self):
        import xlsxwriter

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        base = {"font_name": FONT, "font_size": 10}
        box = dict(base, border=1)
        fmt = {
            "title": wb.add_format(dict(base, font_size=16, bold=True)),
            "plain": wb.add_format(base),
            "company": wb.add_format(dict(base, font_size=11)),
            "yellow": wb.add_format(dict(base, bg_color="#FFFF00")),
            "lbl": wb.add_format(dict(base, bold=True, bg_color="#FFFF80")),
            "val": wb.add_format(dict(base, bg_color="#FFFF80")),
            "head": wb.add_format(dict(box, bold=True, bg_color="#DCE6F1", align="center",
                                       valign="vcenter", text_wrap=True)),
            "group": wb.add_format(dict(box, bold=True, bg_color="#BDE1F2", align="left")),
            "seq": wb.add_format(dict(box, align="center")),
            "text": wb.add_format(box),
            "num": wb.add_format(dict(box, num_format="#,##0.##", align="right")),
            "num_w": wb.add_format(dict(box, num_format="#,##0.##", align="right", bg_color="#FFFFFF")),
            "id": wb.add_format(dict(base, font_size=8, font_color="#A6A6A6")),
            "id_head": wb.add_format(dict(base, font_size=8, font_color="#A6A6A6", align="center")),
            "sig_lbl": wb.add_format(dict(base, bold=True)),
        }
        used = set()
        for rec in self:
            sheet = re.sub(r"[\[\]:*?/\\]", "_", rec.name or "ใบตรวจนับ")[:31]
            while sheet in used:
                sheet = sheet[:28] + "_%d" % len(used)
            used.add(sheet)
            rec._write_count_sheet(wb.add_worksheet(sheet), fmt)
        wb.close()
        return buf.getvalue()

    def _write_count_sheet(self, ws, fmt):
        self.ensure_one()
        show_sys = self._show_system_qty()
        show_cnt = self._show_counted()
        underscores = "_" * 25

        widths = [6.7, 22.7, 55.7, 9.7, 14.7, 15.6, 12.7, 20.7]
        for c, w in enumerate(widths):
            ws.set_column(c, c, w)
        ws.set_column(8, 8, 7, fmt["id"])

        # ---- หัวกระดาษ (แถว 1-6 ตามแบบ) ----
        ws.set_row(0, 25.5)
        ws.write(0, 0, "ใบตรวจนับสินค้าคงคลัง", fmt["title"])
        ws.set_row(1, 16.5)
        ws.write(1, 0, self.company_id.name or "", fmt["company"])
        ws.write(1, 5, "ยอดคงเหลือ ณ วันที่", fmt["plain"])
        ws.write(1, 6, self._snapshot_local() if show_sys else "", fmt["yellow"])

        wh = self.warehouse_id
        wh_label = wh.code or wh.name or ""
        if wh.name and wh.code and wh.name != wh.code:
            wh_label = "%s - %s" % (wh.code, wh.name)
        if self.location_id and self.location_id != wh.lot_stock_id:
            wh_label += " (%s)" % self.location_id.complete_name
        rows = [
            (3, "สาขา / คลังที่นับ", wh_label, "เลขที่ใบนับ", self.name or ""),
            (4, "วันที่นับ", self.date_count.strftime("%d/%m/%Y") if self.date_count else "",
             "รอบการนับ", self._count_type_label()),
            (5, "ผู้นับคนที่ 1", self.counter1 or underscores, "ผู้นับคนที่ 2", self.counter2 or underscores),
        ]
        for r, l1, v1, l2, v2 in rows:
            ws.write(r, 0, l1, fmt["lbl"])
            ws.write(r, 1, "", fmt["lbl"])
            ws.write(r, 2, v1, fmt["val"])
            ws.write(r, 5, l2, fmt["lbl"])
            ws.write(r, 6, v2, fmt["val"])
            ws.write(r, 7, "", fmt["val"])

        # ---- หัวตาราง (แถว 9) ----
        head_row = 8
        heads = ["ลำดับ", "รหัสสินค้า", "ชื่อสินค้า", "หน่วย", "ยอดคงเหลือ", "ยอดตรวจนับ", "ผลต่าง", "หมายเหตุ"]
        for c, h in enumerate(heads):
            ws.write(head_row, c, h, fmt["head"])
        ws.write(head_row, 8, "ID", fmt["id_head"])
        ws.set_row(head_row, 34)

        # ---- รายการ ----
        row = head_row + 1
        seq = 0
        for categ, lines in self._report_groups():
            ws.merge_range(row, 0, row, 7, categ, fmt["group"])
            row += 1
            for line in lines:
                seq += 1
                ws.write(row, 0, seq, fmt["seq"])
                ws.write(row, 1, line.product_id.default_code or "", fmt["text"])
                ws.write(row, 2, line.product_id.name or "", fmt["text"])
                ws.write(row, 3, line.uom_id.name or "", fmt["text"])
                if show_sys:
                    ws.write_number(row, 4, line.qty_system, fmt["num"])
                else:
                    ws.write_blank(row, 4, None, fmt["num"])
                if show_cnt and line.counted:
                    ws.write_number(row, 5, line.qty_counted, fmt["num_w"])
                    if show_sys:
                        ws.write_number(row, 6, line.qty_diff, fmt["num_w"])
                    else:
                        ws.write_blank(row, 6, None, fmt["num_w"])
                else:
                    ws.write_blank(row, 5, None, fmt["num_w"])
                    ws.write_blank(row, 6, None, fmt["num_w"])
                ws.write(row, 7, line.note or "", fmt["text"])
                ws.write_number(row, 8, line.product_id.id, fmt["id"])
                row += 1

        # ---- ลายเซ็น ----
        row += 2
        sig = [(0, "ผู้นับคนที่ 1"), (2, "ผู้นับคนที่ 2"), (4, "ผู้ทาน / หัวหน้าคลัง"), (6, "ผู้อนุมัติ")]
        for c, label in sig:
            ws.write(row, c, label, fmt["sig_lbl"])
            ws.write(row + 2, c, "ลงชื่อ ______________", fmt["plain"])
            ws.write(row + 3, c, "วันที่ ______________", fmt["plain"])

        # ---- หน้ากระดาษ ----
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.repeat_rows(head_row)
        ws.set_margins(left=0.31, right=0.31, top=0.39, bottom=0.39)
        ws.set_footer("&C&\"%s\"หน้า &P / &N" % FONT)
        ws.freeze_panes(head_row + 1, 0)
