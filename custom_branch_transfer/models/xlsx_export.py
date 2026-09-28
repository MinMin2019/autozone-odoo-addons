# -*- coding: utf-8 -*-
"""ปุ่ม Export Excel บนใบโอนสินค้าไปสาขา (BT)

เลือกหลายใบจากหน้า list แล้วสั่งจากเมนู Action ได้ด้วย — 1 ใบ = 1 ชีท
หัวใบ (เลขที่ ต้นทาง สาขา วันที่ สถานะ ใบส่ง/ใบรับ หมายเหตุ) + ตารางสินค้า + แถวรวม
"""
import base64
import io
import re

from odoo import fields, models


class BranchTransfer(models.Model):
    _inherit = "az.branch.transfer"

    def action_export_xlsx(self):
        if not self:
            return False
        data = self._build_transfer_xlsx()
        base = self.name if len(self) == 1 else "BranchTransfer_%s" % fields.Date.context_today(self).strftime("%Y%m%d")
        attachment = self.env["ir.attachment"].create({
            "name": "%s.xlsx" % re.sub(r"[^\w\-.]+", "_", base or "transfer"),
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

    def _build_transfer_xlsx(self):
        import xlsxwriter

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        fmt = {
            "title": wb.add_format({"bold": True, "font_size": 14}),
            "label": wb.add_format({"bold": True}),
            "head": wb.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1,
                                   "align": "center", "valign": "vcenter", "text_wrap": True}),
            "text": wb.add_format({"border": 1}),
            "num": wb.add_format({"border": 1, "num_format": "#,##0.00"}),
            "int": wb.add_format({"border": 1, "align": "center"}),
            "tot_l": wb.add_format({"bold": True, "border": 1, "bg_color": "#F2F2F2"}),
            "tot_n": wb.add_format({"bold": True, "border": 1, "bg_color": "#F2F2F2",
                                    "num_format": "#,##0.00"}),
        }
        used = set()
        for rec in self:
            sheet = re.sub(r"[\[\]:*?/\\]", "_", rec.name or "BT")[:31]
            while sheet in used:
                sheet = sheet[:28] + "_%d" % len(used)
            used.add(sheet)
            rec._write_transfer_sheet(wb.add_worksheet(sheet), fmt)
        wb.close()
        return buf.getvalue()

    def _write_transfer_sheet(self, ws, fmt):
        self.ensure_one()
        state_label = dict(self._fields["state"]._description_selection(self.env)).get(self.state, self.state)
        tins = self.tin_picking_ids
        header = [
            ("เลขที่", self.name or ""),
            ("ต้นทาง (ส่วนกลาง)", self.source_warehouse_id.name or ""),
            ("สาขาปลายทาง", self.warehouse_id.name or ""),
            ("วันที่", self.date.strftime("%d/%m/%Y") if self.date else ""),
            ("สถานะ", state_label),
            ("ผู้สร้าง", self.user_id.name or ""),
            ("ใบส่ง (TOUT)", self.tout_picking_id.name or ""),
            ("ใบรับ (TIN)", ", ".join(tins.mapped("name"))),
            ("หมายเหตุ", self.note or ""),
        ]
        ws.write(0, 0, "%s - ใบโอนสินค้าไปสาขา" % self.company_id.name, fmt["title"])
        row = 2
        for label, value in header:
            # ป้ายกินคอลัมน์ A-B (ลำดับ+รหัส) ค่าอยู่คอลัมน์ C ที่กว้างพอ
            ws.merge_range(row, 0, row, 1, label, fmt["label"])
            ws.write(row, 2, value)
            row += 1
        row += 1

        show_avail = self.state in ("draft", "confirmed")
        show_sent = self.state not in ("draft", "cancel")
        show_recv = self.state in ("sent", "partial", "done")
        cols = [("ลำดับ", 6), ("รหัสสินค้า", 22), ("ชื่อสินค้า", 45), ("หน่วย", 10)]
        if show_avail:
            cols.append(("คงเหลือต้นทาง", 13))
        cols.append(("จำนวนที่ส่ง", 12))
        if show_sent:
            cols.append(("ส่งแล้ว", 12))
        if show_recv:
            cols.append(("สาขารับแล้ว", 12))
        for c, (name, width) in enumerate(cols):
            ws.write(row, c, name, fmt["head"])
            ws.set_column(c, c, width)
        ws.set_row(row, 24)
        first = row + 1
        row = first

        totals = {}
        for i, line in enumerate(self.line_ids, 1):
            values = [
                (i, fmt["int"]),
                (line.product_id.default_code or "", fmt["text"]),
                (line.product_id.name or "", fmt["text"]),
                (line.product_uom_id.name or "", fmt["text"]),
            ]
            if show_avail:
                values.append((line.qty_available_src, fmt["num"]))
            values.append((line.product_uom_qty, fmt["num"]))
            if show_sent:
                values.append((line.qty_sent, fmt["num"]))
            if show_recv:
                values.append((line.qty_received, fmt["num"]))
            for c, (value, f) in enumerate(values):
                ws.write(row, c, value, f)
                if c >= 4 and cols[c][0] != "คงเหลือต้นทาง":
                    totals[c] = totals.get(c, 0.0) + value
            row += 1

        ws.merge_range(row, 0, row, 3, "รวม %d รายการ" % len(self.line_ids), fmt["tot_l"])
        for c in range(4, len(cols)):
            if c in totals:
                ws.write(row, c, totals[c], fmt["tot_n"])
            else:
                ws.write(row, c, "", fmt["tot_l"])
        ws.freeze_panes(first, 0)
