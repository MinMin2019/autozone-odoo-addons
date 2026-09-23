# -*- coding: utf-8 -*-
"""ปุ่ม Export Excel บน stock.picking (ใบรับของ / ใบโอน / ใบเบิกใช้ ทุกประเภท)

ไฟล์ที่ได้: 1 ชีท = หัวใบ (เลขที่ ประเภท สถานะ คู่ค้า ต้นทาง/ปลายทาง วันที่ อ้างอิง ผู้รับผิดชอบ)
ตามด้วยตารางรายการสินค้า (รหัส ชื่อ หมวด Demand Quantity หน่วย Lot/Serial)
คอลัมน์ต้นทุน/มูลค่า แสดงเฉพาะผู้ใช้ที่เป็น Inventory Manager หรือมีสิทธิ์อ่านบัญชี
(ต้นทุนของใบที่ทำเสร็จแล้วอ่านจาก valuation layer, ใบที่ยังไม่เสร็จใช้ต้นทุนปัจจุบัน)
"""
import base64
import io
import re

from odoo import fields, models
from odoo.tools import html2plaintext


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # ------------------------------------------------------------------
    def action_export_xlsx(self):
        self.ensure_one()
        data = self._build_picking_xlsx()
        safe_name = re.sub(r"[^\w\-.]+", "_", self.name or "picking")
        attachment = self.env["ir.attachment"].create({
            "name": "%s.xlsx" % safe_name,
            "type": "binary",
            "datas": base64.b64encode(data),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%d?download=true" % attachment.id,
            "target": "self",
        }

    # ------------------------------------------------------------------
    def _xlsx_can_see_cost(self):
        user = self.env.user
        return user.has_group("stock.group_stock_manager") or user.has_group(
            "account.group_account_readonly"
        )

    def _xlsx_dt(self, dt):
        if not dt:
            return ""
        return fields.Datetime.context_timestamp(self, dt).strftime("%d/%m/%Y %H:%M")

    def _xlsx_move_cost(self, move):
        """ต้นทุนต่อหน่วยของบรรทัด: ใบเสร็จแล้วใช้ค่าจริงจาก valuation layer"""
        if move.state == "done" and "stock_valuation_layer_ids" in move._fields:
            svls = move.sudo().stock_valuation_layer_ids
            qty = sum(abs(s.quantity) for s in svls)
            if qty:
                return sum(abs(s.value) for s in svls) / qty
        return move.product_id.standard_price or 0.0

    def _build_picking_xlsx(self):
        import xlsxwriter

        self.ensure_one()
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet(re.sub(r"[\[\]:*?/\\]", "_", (self.name or "picking"))[:31])

        f_title = wb.add_format({"bold": True, "font_size": 14})
        f_label = wb.add_format({"bold": True})
        f_head = wb.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1,
                                "align": "center", "valign": "vcenter", "text_wrap": True})
        f_text = wb.add_format({"border": 1})
        f_num = wb.add_format({"border": 1, "num_format": "#,##0.00"})
        f_int = wb.add_format({"border": 1, "align": "center"})
        f_tot_l = wb.add_format({"bold": True, "border": 1, "bg_color": "#F2F2F2"})
        f_tot_n = wb.add_format({"bold": True, "border": 1, "bg_color": "#F2F2F2", "num_format": "#,##0.00"})

        state_label = dict(self._fields["state"]._description_selection(self.env)).get(self.state, self.state)
        header = [
            ("เลขที่", self.name or ""),
            ("ประเภทการดำเนินการ", self.picking_type_id.display_name or ""),
            ("สถานะ", state_label),
            ("คู่ค้า", self.partner_id.display_name or ""),
            ("ต้นทาง", self.location_id.complete_name or ""),
            ("ปลายทาง", self.location_dest_id.complete_name or ""),
            ("วันกำหนดการ", self._xlsx_dt(self.scheduled_date)),
            ("วันที่มีผล", self._xlsx_dt(self.date_done)),
        ]
        if "backdate" in self._fields and self.backdate:
            header.append(("วันที่รับจริง (Backdate)", self._xlsx_dt(self.backdate)))
        header += [
            ("เอกสารอ้างอิง", self.origin or ""),
            ("ผู้รับผิดชอบ", self.user_id.name or ""),
            ("หมายเหตุ", html2plaintext(self.note) if self.note else ""),
        ]

        ws.write(0, 0, "%s - %s" % (self.company_id.name, self.picking_type_id.display_name or ""), f_title)
        row = 2
        for label, value in header:
            ws.write(row, 0, label, f_label)
            ws.write(row, 1, value)
            row += 1
        row += 1

        show_cost = self._xlsx_can_see_cost()
        cols = ["ลำดับ", "รหัสสินค้า", "ชื่อสินค้า", "หมวดสินค้า", "Demand", "Quantity", "หน่วย", "Lot/Serial"]
        if show_cost:
            cols += ["ต้นทุน/หน่วย", "มูลค่า"]
        for c, name in enumerate(cols):
            ws.write(row, c, name, f_head)
        ws.set_row(row, 24)
        first = row + 1
        row = first

        tot_demand = tot_qty = tot_value = 0.0
        for i, mv in enumerate(self.move_ids.filtered(lambda m: m.state != "cancel"), 1):
            lots = ", ".join(sorted({ml.lot_id.name or ml.lot_name or "" for ml in mv.move_line_ids} - {""}))
            ws.write(row, 0, i, f_int)
            ws.write(row, 1, mv.product_id.default_code or "", f_text)
            ws.write(row, 2, mv.product_id.name or "", f_text)
            ws.write(row, 3, mv.product_id.categ_id.complete_name or "", f_text)
            ws.write(row, 4, mv.product_uom_qty, f_num)
            ws.write(row, 5, mv.quantity, f_num)
            ws.write(row, 6, mv.product_uom.name or "", f_text)
            ws.write(row, 7, lots, f_text)
            tot_demand += mv.product_uom_qty
            tot_qty += mv.quantity
            if show_cost:
                cost = self._xlsx_move_cost(mv)
                qty_for_value = mv.quantity if mv.state == "done" else mv.product_uom_qty
                value = cost * qty_for_value
                tot_value += value
                ws.write(row, 8, cost, f_num)
                ws.write(row, 9, value, f_num)
            row += 1

        ws.merge_range(row, 0, row, 3, "รวม", f_tot_l)
        ws.write(row, 4, tot_demand, f_tot_n)
        ws.write(row, 5, tot_qty, f_tot_n)
        ws.write(row, 6, "", f_tot_l)
        ws.write(row, 7, "", f_tot_l)
        if show_cost:
            ws.write(row, 8, "", f_tot_l)
            ws.write(row, 9, tot_value, f_tot_n)

        widths = [6, 18, 45, 30, 11, 11, 10, 18, 13, 14]
        for c, w in enumerate(widths[: len(cols)]):
            ws.set_column(c, c, w)
        ws.set_column(1, 1, 22)  # หัวใบ: ค่าอยู่คอลัมน์ B
        ws.freeze_panes(first, 0)
        wb.close()
        return buf.getvalue()
