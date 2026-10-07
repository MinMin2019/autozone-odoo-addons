# -*- coding: utf-8 -*-
"""รายงานใบสั่งซื้อรายบรรทัดตามเดือน

เลือกเดือน/ปี -> ดูบนจอ (list purchase.order.line) หรือ Export Excel
ช่วงเดือนคิดจาก date_order ของ PO ตาม timezone ผู้ใช้ (default Asia/Bangkok) แปลงเป็น UTC ก่อนค้น
"""
import base64
import calendar
import io
from datetime import datetime, time

import pytz

from odoo import _, fields, models
from odoo.exceptions import UserError

MONTHS = [
    ("1", "มกราคม"), ("2", "กุมภาพันธ์"), ("3", "มีนาคม"), ("4", "เมษายน"),
    ("5", "พฤษภาคม"), ("6", "มิถุนายน"), ("7", "กรกฎาคม"), ("8", "สิงหาคม"),
    ("9", "กันยายน"), ("10", "ตุลาคม"), ("11", "พฤศจิกายน"), ("12", "ธันวาคม"),
]


class AzPurchaseLineReportWizard(models.TransientModel):
    _name = "az.purchase.line.report.wizard"
    _description = "รายงานใบสั่งซื้อรายบรรทัดตามเดือน"

    month = fields.Selection(MONTHS, "เดือน", required=True,
                             default=lambda self: str(fields.Date.context_today(self).month))
    year = fields.Integer("ปี (ค.ศ.)", required=True,
                          default=lambda self: fields.Date.context_today(self).year)
    state_filter = fields.Selection([
        ("confirmed", "เฉพาะ PO ที่ยืนยันแล้ว"),
        ("all", "ทุกสถานะ (รวม RFQ ยังไม่ยืนยัน)"),
    ], "สถานะ PO", required=True, default="confirmed")
    company_ids = fields.Many2many("res.company", string="บริษัท",
                                   default=lambda self: self.env.companies)

    # ------------------------------------------------------------------
    def _utc_range(self):
        self.ensure_one()
        if not 2000 <= self.year <= 2100:
            raise UserError(_("ปีต้องเป็น ค.ศ. เช่น 2026 (ไม่ใช่ พ.ศ.)"))
        m = int(self.month)
        last = calendar.monthrange(self.year, m)[1]
        tz = pytz.timezone(self.env.user.tz or "Asia/Bangkok")
        start = tz.localize(datetime(self.year, m, 1)).astimezone(pytz.utc).replace(tzinfo=None)
        end = tz.localize(datetime.combine(datetime(self.year, m, last).date(), time.max)) \
            .astimezone(pytz.utc).replace(tzinfo=None)
        return start, end

    def _line_domain(self):
        start, end = self._utc_range()
        domain = [
            ("display_type", "=", False),
            ("order_id.date_order", ">=", fields.Datetime.to_string(start)),
            ("order_id.date_order", "<=", fields.Datetime.to_string(end)),
            ("state", "!=", "cancel"),
        ]
        if self.state_filter == "confirmed":
            domain.append(("state", "in", ("purchase", "done")))
        if self.company_ids:
            domain.append(("company_id", "in", self.company_ids.ids))
        return domain

    def _period_label(self):
        return "%s %d" % (dict(MONTHS)[self.month], self.year)

    # ------------------------------------------------------------------
    def action_view(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("รายการสั่งซื้อ %s") % self._period_label(),
            "res_model": "purchase.order.line",
            "view_mode": "list",
            "views": [(self.env.ref("custom_purchase_line_report.az_purchase_line_report_list").id, "list")],
            "search_view_id": self.env.ref("purchase.purchase_order_line_search").id,
            "domain": self._line_domain(),
            "context": {"create": False, "edit": False, "delete": False},
        }

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self.env["purchase.order.line"].search(self._line_domain())
        if not lines:
            raise UserError(_("ไม่มีรายการสั่งซื้อใน %s") % self._period_label())
        lines = lines.sorted(lambda l: (l.order_id.date_order or datetime.min, l.order_id.name or "",
                                        l.sequence, l.id))
        data = self._build_xlsx(lines)
        attachment = self.env["ir.attachment"].create({
            "name": "PO_lines_%d-%02d.xlsx" % (self.year, int(self.month)),
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

    def _build_xlsx(self, lines):
        import xlsxwriter

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("PO %d-%02d" % (self.year, int(self.month)))

        f_title = wb.add_format({"bold": True, "font_size": 14})
        f_head = wb.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1,
                                "align": "center", "valign": "vcenter", "text_wrap": True})
        f_text = wb.add_format({"border": 1})
        f_date = wb.add_format({"border": 1, "num_format": "dd/mm/yyyy", "align": "center"})
        f_num = wb.add_format({"border": 1, "num_format": "#,##0.00"})
        f_tot_l = wb.add_format({"bold": True, "border": 1, "bg_color": "#F2F2F2"})
        f_tot_n = wb.add_format({"bold": True, "border": 1, "bg_color": "#F2F2F2", "num_format": "#,##0.00"})

        state_label = dict(self.env["purchase.order"]._fields["state"]._description_selection(self.env))
        filter_label = dict(self._fields["state_filter"]._description_selection(self.env))
        ws.write(0, 0, "รายงานใบสั่งซื้อรายบรรทัด เดือน %s" % self._period_label(), f_title)
        ws.write(1, 0, "สถานะ: %s   |   %d บรรทัด จาก %d ใบ" % (
            filter_label[self.state_filter], len(lines), len(lines.order_id)))

        heads = [
            ("เลข PO", 14), ("วันที่", 11), ("ผู้ขาย", 34), ("รหัสสินค้า", 16), ("สินค้า", 40),
            ("จำนวนสั่ง", 11), ("จำนวนรับแล้ว", 11), ("หน่วย", 8), ("ราคาต่อหน่วย", 13),
            ("ยอดรวม (ก่อน VAT)", 15), ("ยอดรวม (รวม VAT)", 15), ("สถานะ PO", 12),
        ]
        hr = 3
        for c, (h, w) in enumerate(heads):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, w)
        ws.set_row(hr, 30)
        ws.freeze_panes(hr + 1, 1)

        r = hr + 1
        for line in lines:
            order = line.order_id
            ws.write(r, 0, order.name or "", f_text)
            if order.date_order:
                d = fields.Datetime.context_timestamp(self, order.date_order).replace(tzinfo=None)
                ws.write_datetime(r, 1, d, f_date)
            else:
                ws.write(r, 1, "", f_text)
            ws.write(r, 2, order.partner_id.display_name or "", f_text)
            ws.write(r, 3, line.product_id.default_code or "", f_text)
            ws.write(r, 4, line.product_id.name or line.name or "", f_text)
            ws.write_number(r, 5, line.product_qty, f_num)
            ws.write_number(r, 6, line.qty_received, f_num)
            ws.write(r, 7, line.product_uom.name or "", f_text)
            ws.write_number(r, 8, line.price_unit, f_num)
            ws.write_number(r, 9, line.price_subtotal, f_num)
            ws.write_number(r, 10, line.price_total, f_num)
            ws.write(r, 11, state_label.get(order.state, order.state or ""), f_text)
            r += 1

        # แถวรวม: สูตร =SUM (ใส่ค่าที่คำนวณไว้ด้วย เผื่อโปรแกรมที่ไม่คำนวณสูตรเอง)
        first, last = hr + 2, r
        ws.write(r, 0, "รวม", f_tot_l)
        for c in (1, 2, 3, 4, 7, 8, 11):
            ws.write(r, c, "", f_tot_l)
        for c, col, fname in ((5, "F", "product_qty"), (6, "G", "qty_received"),
                              (9, "J", "price_subtotal"), (10, "K", "price_total")):
            ws.write_formula(r, c, "=SUM(%s%d:%s%d)" % (col, first, col, last), f_tot_n,
                             sum(lines.mapped(fname)))
        ws.autofilter(hr, 0, r - 1, len(heads) - 1)

        wb.close()
        return buf.getvalue()
