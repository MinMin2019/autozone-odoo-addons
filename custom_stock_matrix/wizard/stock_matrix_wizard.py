# -*- coding: utf-8 -*-
"""Stock Matrix สินค้า × สาขา ณ วันที่

* ยอดคงเหลือต่อ (สินค้า, สาขา) จาก stock.move.line done (กติกาเดียวกับ Stock Card)
* มูลค่า = จำนวน x standard_price ปัจจุบัน (ต้นทุนมาตรฐาน)
* เก็บเป็น cell (สินค้า × สาขา) แล้วให้ pivot ของ Odoo จัดเป็นตาราง; Excel/PDF สร้างตารางเอง
"""
import base64
import io
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def thai_date(d):
    if not d:
        return ""
    return "%02d/%02d/%d" % (d.day, d.month, d.year + 543)


def wh_sort_key(w):
    """H.O. ก่อน แล้วเรียงตามชื่อ"""
    n = (w.name or "").upper()
    return (0 if n.replace(".", "") in ("HO", "H O") else 1, n)


class StockMatrixWizard(models.TransientModel):
    _name = "stock.matrix.wizard"
    _description = "Stock Matrix สินค้า × สาขา"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_to = fields.Date("ณ วันที่", required=True, default=fields.Date.context_today)
    warehouse_ids = fields.Many2many("stock.warehouse", string="สาขา / คลัง", help="เว้นว่าง = ทุกสาขาที่มีสิทธิ์เห็น")
    product_ids = fields.Many2many("product.product", string="สินค้า")
    categ_ids = fields.Many2many("product.category", string="หมวดสินค้า")
    measure = fields.Selection([("qty", "จำนวน"), ("value", "มูลค่า")], string="ตัวเลขใน PDF", default="qty", required=True)
    include_zero_products = fields.Boolean("รวมสินค้าที่ไม่มีของทุกสาขา")
    include_non_storable = fields.Boolean("รวมสินค้าที่ไม่เก็บสต็อก")
    only_negative_or_multi = fields.Boolean("เฉพาะสินค้าที่มีของมากกว่า 1 สาขา หรือมีสาขาติดลบ",
                                            help="ใช้หาโอกาสโยกของระหว่างสาขา")
    cell_ids = fields.One2many("stock.matrix.cell", "wizard_id")
    cell_count = fields.Integer(compute="_compute_cell_count")

    @api.depends("date_to")
    def _compute_name(self):
        for w in self:
            w.name = "Stock Matrix ณ %s" % thai_date(w.date_to)

    @api.depends("cell_ids")
    def _compute_cell_count(self):
        for w in self:
            w.cell_count = len(w.cell_ids)

    # ------------------------------------------------------------------
    def _get_scope_warehouses(self):
        self.ensure_one()
        whs = self.warehouse_ids or self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)])
        user = self.env.user
        if "allowed_warehouse_ids" in user._fields and user.allowed_warehouse_ids and not user.warehouse_unrestricted:
            whs = whs & user.allowed_warehouse_ids
        if not whs:
            raise UserError(_("ไม่มีสาขา/คลังที่มีสิทธิ์ดูในขอบเขตที่เลือก"))
        return whs

    def _get_scope_products(self):
        self.ensure_one()
        Product = self.env["product.product"].with_context(active_test=False)
        if self.product_ids:
            products = self.product_ids
        else:
            domain = [("company_id", "in", [False, self.company_id.id])]
            if self.categ_ids:
                domain.append(("categ_id", "child_of", self.categ_ids.ids))
            products = Product.search(domain)
        if not self.include_non_storable:
            products = products.filtered("is_storable")
        return products

    def _utc_end(self):
        tz = pytz.timezone(self.env.user.tz or "Asia/Bangkok")
        return tz.localize(datetime.combine(self.date_to + timedelta(days=1), time.min)).astimezone(pytz.utc).replace(tzinfo=None)

    def sorted_warehouses(self):
        self.ensure_one()
        whs = self.cell_ids.mapped("warehouse_id")
        return whs.sorted(key=wh_sort_key)

    # ------------------------------------------------------------------
    def action_compute(self):
        self.ensure_one()
        self.cell_ids.unlink()
        warehouses = self._get_scope_warehouses()
        products = self._get_scope_products()
        if not products:
            raise UserError(_("ไม่พบสินค้าตามเงื่อนไขที่เลือก"))
        end = self._utc_end()
        self.env.flush_all()
        params = {"company": self.company_id.id, "end": end, "products": products.ids, "wh": warehouses.ids}
        base = """
                 FROM stock_move_line ml
                 JOIN stock_move m ON m.id = ml.move_id
                 JOIN stock_location ls ON ls.id = ml.location_id
                 JOIN stock_location ld ON ld.id = ml.location_dest_id
                WHERE ml.state = 'done' AND m.company_id = %(company)s AND ml.date < %(end)s
                  AND ml.product_id = ANY(%(products)s)
                  AND NOT (ls.usage = 'internal' AND ld.usage = 'internal' AND ls.warehouse_id = ld.warehouse_id)
        """
        raw = defaultdict(float)
        # ฝั่งรับเข้า (+)
        self.env.cr.execute(
            "SELECT ml.product_id, ld.warehouse_id, COALESCE(SUM(ml.quantity_product_uom), 0)" + base
            + " AND ld.usage = 'internal' AND ld.warehouse_id = ANY(%(wh)s) GROUP BY ml.product_id, ld.warehouse_id",
            params,
        )
        for pid, wh, qty in self.env.cr.fetchall():
            raw[(pid, wh)] += qty
        # ฝั่งจ่ายออก (−)
        self.env.cr.execute(
            "SELECT ml.product_id, ls.warehouse_id, COALESCE(SUM(ml.quantity_product_uom), 0)" + base
            + " AND ls.usage = 'internal' AND ls.warehouse_id = ANY(%(wh)s) GROUP BY ml.product_id, ls.warehouse_id",
            params,
        )
        for pid, wh, qty in self.env.cr.fetchall():
            raw[(pid, wh)] -= qty

        products = products.with_company(self.company_id)
        prod_by_id = {p.id: p for p in products}
        per_prod = defaultdict(dict)
        for (pid, wh), qty in raw.items():
            if wh and abs(qty) > 1e-6:
                per_prod[pid][wh] = qty
        vals = []
        wh_by_id = {w.id: w for w in warehouses}
        for pid, cells in per_prod.items():
            p = prod_by_id.get(pid)
            if p is None:
                continue
            nonzero = {wh: q for wh, q in cells.items() if abs(q) > 1e-6}
            if not nonzero and not self.include_zero_products:
                continue
            if self.only_negative_or_multi:
                if len([q for q in nonzero.values() if q > 0]) < 2 and not any(q < 0 for q in nonzero.values()):
                    continue
            cost = p.standard_price or 0.0
            total = sum(nonzero.values())
            holders = len([q for q in nonzero.values() if q > 0])
            for wh, q in nonzero.items():
                vals.append({
                    "wizard_id": self.id, "product_id": pid, "default_code": p.default_code or "",
                    "product_name": p.name, "categ_id": p.categ_id.id, "uom_id": p.uom_id.id,
                    "warehouse_id": wh, "qty": q, "unit_cost": cost, "value": q * cost,
                    "product_total_qty": total, "holder_count": holders,
                })
        cells = self.env["stock.matrix.cell"].create(vals)
        _logger.info("stock matrix: %d cells", len(cells))
        return cells

    def _ensure_cells(self):
        self.ensure_one()
        if not self.cell_ids:
            self.action_compute()
        return self.cell_ids

    # ------------------------------------------------------------------
    def action_view(self):
        self.ensure_one()
        self.action_compute()
        return {
            "type": "ir.actions.act_window", "name": self.name, "res_model": "stock.matrix.cell",
            "view_mode": "pivot,list,graph", "domain": [("wizard_id", "=", self.id)],
            "context": {"create": False, "edit": False, "delete": False,
                        "pivot_measures": ["qty"], "pivot_row_groupby": ["product_id"],
                        "pivot_column_groupby": ["warehouse_id"]},
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._ensure_cells()
        return self.env.ref("custom_stock_matrix.action_report_stock_matrix").report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        cells = self._ensure_cells()
        data = self._build_xlsx(cells)
        attachment = self.env["ir.attachment"].create({
            "name": "StockMatrix_%s.xlsx" % self.date_to.strftime("%Y%m%d"), "type": "binary",
            "datas": base64.b64encode(data), "res_model": self._name, "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%d?download=true" % attachment.id, "target": "self"}

    def thai_date(self, d):
        return thai_date(d)

    def matrix_rows(self, measure=None):
        """[(product_info, {wh_id: value}, total)] เรียงตามหมวด/รหัส"""
        self.ensure_one()
        measure = measure or self.measure
        rows = {}
        for c in self.cell_ids:
            r = rows.setdefault(c.product_id.id, {
                "code": c.default_code or "", "name": c.product_name or "", "uom": c.uom_id.name or "",
                "categ": c.categ_id.complete_name or "", "cells": {}, "total": 0.0, "holders": c.holder_count,
            })
            v = c.qty if measure == "qty" else c.value
            r["cells"][c.warehouse_id.id] = v
            r["total"] += v
        return sorted(rows.values(), key=lambda r: (r["categ"], r["code"], r["name"]))

    def column_totals(self, measure=None):
        """{wh_id: total} สำหรับ PDF"""
        self.ensure_one()
        measure = measure or self.measure
        tot = defaultdict(float)
        for c in self.cell_ids:
            tot[c.warehouse_id.id] += c.qty if measure == "qty" else c.value
        return dict(tot)

    def warehouse_chunks(self, size=13):
        whs = list(self.sorted_warehouses())
        return [whs[i:i + size] for i in range(0, len(whs), size)]

    # ------------------------------------------------------------------
    def _build_xlsx(self, cells):
        import xlsxwriter

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        f_title = wb.add_format({"bold": True, "font_size": 14})
        f_head = wb.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1, "align": "center",
                                "valign": "vcenter", "text_wrap": True})
        f_text = wb.add_format({"border": 1})
        f_num = wb.add_format({"border": 1, "num_format": "#,##0.00;[Red]-#,##0.00;\"\""})
        f_int = wb.add_format({"border": 1, "num_format": "0"})
        f_tot = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA", "num_format": "#,##0.00;[Red]-#,##0.00"})
        whs = list(self.sorted_warehouses())
        sub = "ณ วันที่ %s | %d สินค้า × %d สาขา" % (self.date_to.strftime("%d/%m/%Y"), len(set(cells.mapped("product_id.id"))), len(whs))

        def matrix_sheet(title, measure):
            ws = wb.add_worksheet(title)
            ws.write(0, 0, "Stock Matrix สินค้า × สาขา (%s)" % title, f_title)
            ws.write(1, 0, sub)
            hr = 3
            heads = ["รหัสสินค้า", "ชื่อสินค้า", "หมวด", "หน่วย", "สาขาที่มี"] + [w.name for w in whs] + ["รวม"]
            widths = [14, 36, 22, 8, 8] + [10] * len(whs) + [12]
            for c, (h, wd) in enumerate(zip(heads, widths)):
                ws.write(hr, c, h, f_head)
                ws.set_column(c, c, wd)
            ws.freeze_panes(hr + 1, 5)
            r = hr + 1
            rows = self.matrix_rows(measure)
            first = r + 1
            for row in rows:
                ws.write(r, 0, row["code"], f_text)
                ws.write(r, 1, row["name"], f_text)
                ws.write(r, 2, row["categ"], f_text)
                ws.write(r, 3, row["uom"], f_text)
                ws.write_number(r, 4, row["holders"], f_int)
                for i, w in enumerate(whs):
                    ws.write_number(r, 5 + i, row["cells"].get(w.id, 0.0), f_num)
                col_first = xlsxwriter.utility.xl_col_to_name(5)
                col_last = xlsxwriter.utility.xl_col_to_name(5 + len(whs) - 1)
                ws.write_formula(r, 5 + len(whs), "=SUM(%s%d:%s%d)" % (col_first, r + 1, col_last, r + 1), f_tot)
                r += 1
            if rows:
                ws.write(r, 0, "รวม", f_tot)
                for c in range(1, 5):
                    ws.write(r, c, "", f_tot)
                for i in range(len(whs) + 1):
                    col = xlsxwriter.utility.xl_col_to_name(5 + i)
                    ws.write_formula(r, 5 + i, "=SUM(%s%d:%s%d)" % (col, first, col, r), f_tot)
            ws.autofilter(hr, 0, max(r - 1, hr), len(heads) - 1)

        matrix_sheet("จำนวน", "qty")
        matrix_sheet("มูลค่า", "value")

        ws = wb.add_worksheet("ข้อมูลดิบ")
        ws.write(0, 0, "Stock Matrix - ข้อมูลดิบ (1 บรรทัด = สินค้า × สาขา)", f_title)
        ws.write(1, 0, sub)
        heads = [("สาขา", 12), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 36), ("หมวด", 22), ("หน่วย", 8),
                 ("จำนวน", 11), ("ต้นทุน/หน่วย", 11), ("มูลค่า", 13), ("รวมทุกสาขา (จำนวน)", 12), ("สาขาที่มี", 8)]
        hr = 3
        for c, (h, wd) in enumerate(heads):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, wd)
        ws.freeze_panes(hr + 1, 3)
        r = hr + 1
        for c_ in cells:
            ws.write(r, 0, c_.warehouse_id.name or "", f_text)
            ws.write(r, 1, c_.default_code or "", f_text)
            ws.write(r, 2, c_.product_name or "", f_text)
            ws.write(r, 3, c_.categ_id.complete_name or "", f_text)
            ws.write(r, 4, c_.uom_id.name or "", f_text)
            ws.write_number(r, 5, c_.qty, f_num)
            ws.write_number(r, 6, c_.unit_cost, f_num)
            ws.write_number(r, 7, c_.value, f_num)
            ws.write_number(r, 8, c_.product_total_qty, f_num)
            ws.write_number(r, 9, c_.holder_count, f_int)
            r += 1
        ws.autofilter(hr, 0, max(r - 1, hr), len(heads) - 1)
        wb.close()
        return buf.getvalue()


class StockMatrixCell(models.TransientModel):
    _name = "stock.matrix.cell"
    _description = "Stock Matrix - สินค้า × สาขา"
    _order = "categ_id, default_code, product_id, warehouse_id, id"

    wizard_id = fields.Many2one("stock.matrix.wizard", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", "สินค้า", required=True)
    default_code = fields.Char("รหัสสินค้า")
    product_name = fields.Char("ชื่อสินค้า")
    categ_id = fields.Many2one("product.category", "หมวด")
    uom_id = fields.Many2one("uom.uom", "หน่วย")
    warehouse_id = fields.Many2one("stock.warehouse", "สาขา / คลัง", required=True)
    qty = fields.Float("จำนวน", digits=(16, 2))
    unit_cost = fields.Float("ต้นทุน/หน่วย", digits=(16, 2))
    value = fields.Float("มูลค่า", digits=(16, 2))
    product_total_qty = fields.Float("รวมทุกสาขา", digits=(16, 2))
    holder_count = fields.Integer("สาขาที่มี")
    date_to = fields.Date(related="wizard_id.date_to")
