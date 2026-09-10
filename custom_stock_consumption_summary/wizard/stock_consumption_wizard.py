# -*- coding: utf-8 -*-
"""สรุปเบิกใช้วัสดุตามสาขา / บัญชีค่าใช้จ่าย

แหล่งข้อมูล (source)
  cons   = internal → location ที่ is_expense_consumption (ใบเบิกใช้วัสดุ CONS) ; เบิกคืนกลับทางเดียวกัน = ติดลบ
  legacy = internal → customer ที่ sale line ราคา 0 (วิธีเดิม SO 0 บาท) ; คืนจากลูกค้าราคา 0 = ติดลบ
มูลค่า = qty × ต้นทุน SVL ของ move (ถ้าไม่มีใช้ standard_price)
บัญชีค่าใช้จ่าย = product_tmpl.get_product_accounts()['expense'] (สินค้า > หมวด) ตัวเดียวกับที่ JE เบิกใช้ลง
สาขา (analytic) = consumption_analytic_account_id ของ operation type CONS ของคลังต้นทาง
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


class StockConsumptionWizard(models.TransientModel):
    _name = "stock.consumption.wizard"
    _description = "สรุปเบิกใช้วัสดุตามสาขา"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_from = fields.Date("ตั้งแต่วันที่", required=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date("ถึงวันที่", required=True, default=fields.Date.context_today)
    warehouse_ids = fields.Many2many("stock.warehouse", string="สาขา / คลัง", help="เว้นว่าง = ทุกสาขาที่มีสิทธิ์เห็น")
    product_ids = fields.Many2many("product.product", string="สินค้า")
    categ_ids = fields.Many2many("product.category", string="หมวดสินค้า")
    include_legacy = fields.Boolean("รวมส่งขายราคา 0 (วิธีเดิมก่อนมีใบเบิกใช้)", default=True)
    line_ids = fields.One2many("stock.consumption.line", "wizard_id")
    line_count = fields.Integer(compute="_compute_line_count")

    @api.depends("date_from", "date_to")
    def _compute_name(self):
        for w in self:
            w.name = "สรุปเบิกใช้วัสดุ %s - %s" % (thai_date(w.date_from), thai_date(w.date_to))

    @api.depends("line_ids")
    def _compute_line_count(self):
        for w in self:
            w.line_count = len(w.line_ids)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for w in self:
            if w.date_from and w.date_to and w.date_from > w.date_to:
                raise UserError(_("วันที่เริ่มต้องไม่เกินวันที่สิ้นสุด"))

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

    def _tz(self):
        return pytz.timezone(self.env.user.tz or "Asia/Bangkok")

    def _to_utc(self, d):
        return self._tz().localize(datetime.combine(d, time.min)).astimezone(pytz.utc).replace(tzinfo=None)

    def _local_date(self, dt):
        return pytz.utc.localize(dt).astimezone(self._tz()).date()

    # ------------------------------------------------------------------
    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        warehouses = self._get_scope_warehouses()
        start, end = self._to_utc(self.date_from), self._to_utc(self.date_to + timedelta(days=1))
        product_ids = None
        if self.product_ids or self.categ_ids:
            dom = [("company_id", "in", [False, self.company_id.id])]
            if self.product_ids:
                dom.append(("id", "in", self.product_ids.ids))
            if self.categ_ids:
                dom.append(("categ_id", "child_of", self.categ_ids.ids))
            product_ids = self.env["product.product"].with_context(active_test=False).search(dom).ids

        query = """
            SELECT ml.date, ml.product_id, ml.quantity_product_uom AS qty, ml.reference, m.origin,
                   ls.usage AS src_usage, ld.usage AS dst_usage,
                   ls.warehouse_id AS src_wh, ld.warehouse_id AS dst_wh,
                   ls.is_expense_consumption AS src_cons, ld.is_expense_consumption AS dst_cons,
                   sol.price_unit AS sol_price, svl.unit_cost,
                   COALESCE(p.user_id, m.create_uid) AS user_id
              FROM stock_move_line ml
              JOIN stock_move m ON m.id = ml.move_id
              JOIN stock_location ls ON ls.id = ml.location_id
              JOIN stock_location ld ON ld.id = ml.location_dest_id
         LEFT JOIN stock_picking p ON p.id = ml.picking_id
         LEFT JOIN sale_order_line sol ON sol.id = m.sale_line_id
         LEFT JOIN (SELECT stock_move_id,
                           CASE WHEN SUM(quantity) <> 0 THEN SUM(value) / SUM(quantity) END AS unit_cost
                      FROM stock_valuation_layer WHERE stock_move_id IS NOT NULL GROUP BY stock_move_id) svl
                ON svl.stock_move_id = m.id
             WHERE ml.state = 'done' AND m.company_id = %(company)s
               AND ml.date >= %(start)s AND ml.date < %(end)s
               AND (
                    (ls.usage = 'internal' AND ld.is_expense_consumption AND ls.warehouse_id = ANY(%(wh)s))
                 OR (ld.usage = 'internal' AND ls.is_expense_consumption AND ld.warehouse_id = ANY(%(wh)s))
                 OR (%(legacy)s AND ls.usage = 'internal' AND ld.usage = 'customer'
                     AND sol.price_unit IS NOT NULL AND sol.price_unit = 0 AND ls.warehouse_id = ANY(%(wh)s))
                 OR (%(legacy)s AND ld.usage = 'internal' AND ls.usage = 'customer'
                     AND sol.price_unit IS NOT NULL AND sol.price_unit = 0 AND ld.warehouse_id = ANY(%(wh)s))
               )
        """
        params = {"company": self.company_id.id, "start": start, "end": end, "wh": warehouses.ids,
                  "legacy": bool(self.include_legacy)}
        if product_ids is not None:
            query += " AND ml.product_id = ANY(%(products)s)"
            params["products"] = product_ids
        query += " ORDER BY ml.date, ml.id"
        self.env.flush_all()
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()

        Product = self.env["product.product"].with_context(active_test=False).with_company(self.company_id)
        prod_by_id = {p.id: p for p in Product.browse({r["product_id"] for r in rows})}
        std_cost = {pid: (p.standard_price or 0.0) for pid, p in prod_by_id.items()}
        expense_by_tmpl = {}

        def expense_account(p):
            t = p.product_tmpl_id
            if t.id not in expense_by_tmpl:
                accs = t.with_company(self.company_id).get_product_accounts()
                expense_by_tmpl[t.id] = accs.get("expense")
            return expense_by_tmpl[t.id]

        cons_types = self.env["stock.picking.type"].search(
            [("sequence_code", "=", "CONS"), ("warehouse_id", "in", warehouses.ids)])
        analytic_by_wh = {t.warehouse_id.id: t.consumption_analytic_account_id for t in cons_types}
        wh_by_id = {w.id: w for w in warehouses}

        agg = {}
        for r in rows:
            if r["src_usage"] == "internal":
                wh, sign = r["src_wh"], 1
            else:
                wh, sign = r["dst_wh"], -1
            if r["dst_cons"] or r["src_cons"]:
                source = "cons"
            else:
                source = "legacy"
            p = prod_by_id.get(r["product_id"])
            if p is None or wh not in wh_by_id:
                continue
            cost = r["unit_cost"]
            if cost is None:
                cost = std_cost.get(p.id, 0.0)
            cost = abs(cost)
            d = self._local_date(r["date"])
            month = "%04d-%02d" % (d.year, d.month)
            key = (wh, p.id, source, month)
            a = agg.setdefault(key, {"qty": 0.0, "value": 0.0, "ret_qty": 0.0, "ret_value": 0.0, "moves": 0})
            q = (r["qty"] or 0.0) * sign
            a["qty"] += q
            a["value"] += q * cost
            if sign < 0:
                a["ret_qty"] += -q
                a["ret_value"] += -q * cost
            a["moves"] += 1

        vals = []
        for (wh, pid, source, month), a in agg.items():
            p = prod_by_id[pid]
            acc = expense_account(p)
            analytic = analytic_by_wh.get(wh)
            vals.append({
                "wizard_id": self.id, "warehouse_id": wh, "analytic_account_id": analytic.id if analytic else False,
                "product_id": pid, "default_code": p.default_code or "", "product_name": p.name,
                "categ_id": p.categ_id.id, "uom_id": p.uom_id.id,
                "expense_account_id": acc.id if acc else False,
                "expense_code": acc.code if acc else "", "expense_name": acc.name if acc else "ไม่ได้ตั้งบัญชีค่าใช้จ่าย",
                "source": source, "month": month,
                "qty": a["qty"], "value": a["value"], "return_qty": a["ret_qty"], "return_value": a["ret_value"],
                "move_count": a["moves"],
            })
        lines = self.env["stock.consumption.line"].create(vals)
        _logger.info("consumption summary: %d rows -> %d lines", len(rows), len(lines))
        return lines

    def _ensure_lines(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_compute()
        return self.line_ids

    # ------------------------------------------------------------------
    def action_view(self):
        self.ensure_one()
        self.action_compute()
        return {
            "type": "ir.actions.act_window", "name": self.name, "res_model": "stock.consumption.line",
            "view_mode": "pivot,list,graph", "domain": [("wizard_id", "=", self.id)],
            "context": {"create": False, "edit": False, "delete": False,
                        "pivot_measures": ["value"], "pivot_row_groupby": ["warehouse_id"],
                        "pivot_column_groupby": ["expense_account_id"]},
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._ensure_lines()
        return self.env.ref("custom_stock_consumption_summary.action_report_stock_consumption").report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self._ensure_lines()
        data = self._build_xlsx(lines)
        attachment = self.env["ir.attachment"].create({
            "name": "Consumption_%s_%s.xlsx" % (self.date_from.strftime("%Y%m%d"), self.date_to.strftime("%Y%m%d")),
            "type": "binary", "datas": base64.b64encode(data), "res_model": self._name, "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%d?download=true" % attachment.id, "target": "self"}

    def thai_date(self, d):
        return thai_date(d)

    # ---------- สรุปสำหรับ PDF/Excel ----------
    def expense_columns(self):
        """[(account_id or False, code, name)] เรียงตามรหัส"""
        seen = {}
        for l in self.line_ids:
            seen[l.expense_account_id.id or False] = (l.expense_code or "", l.expense_name or "")
        return sorted(((k, v[0], v[1]) for k, v in seen.items()), key=lambda x: (x[1] == "", x[1]))

    def matrix(self, row_field):
        """{row_key: {'label': .., 'cells': {acc_id: value}, 'total': v, 'cons': v, 'legacy': v}} เรียงตาม label"""
        rows = {}
        for l in self.line_ids:
            rec = l[row_field]
            k = rec.id if rec else False
            label = (rec.complete_name if row_field == "categ_id" else rec.display_name) if rec else "-"
            r = rows.setdefault(k, {"label": label, "cells": defaultdict(float), "total": 0.0, "cons": 0.0, "legacy": 0.0})
            r["cells"][l.expense_account_id.id or False] += l.value
            r["total"] += l.value
            r[l.source] += l.value
        return sorted(rows.values(), key=lambda r: r["label"])

    def column_totals(self):
        tot = defaultdict(float)
        for l in self.line_ids:
            tot[l.expense_account_id.id or False] += l.value
        return dict(tot)

    def grand_total(self):
        return sum(self.line_ids.mapped("value"))

    def source_totals(self):
        out = {"cons": 0.0, "legacy": 0.0}
        for l in self.line_ids:
            out[l.source] += l.value
        return out

    # ------------------------------------------------------------------
    def _build_xlsx(self, lines):
        import xlsxwriter

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        f_title = wb.add_format({"bold": True, "font_size": 14})
        f_head = wb.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1, "align": "center",
                                "valign": "vcenter", "text_wrap": True})
        f_text = wb.add_format({"border": 1})
        f_num = wb.add_format({"border": 1, "num_format": "#,##0.00;[Red]-#,##0.00;\"\""})
        f_tot = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA", "num_format": "#,##0.00;[Red]-#,##0.00"})
        sub = "%s ถึง %s%s" % (self.date_from.strftime("%d/%m/%Y"), self.date_to.strftime("%d/%m/%Y"),
                                " | รวมส่งขายราคา 0 (วิธีเดิม)" if self.include_legacy else "")
        cols = self.expense_columns()

        def matrix_sheet(title, row_field, first_head):
            ws = wb.add_worksheet(title)
            ws.write(0, 0, "สรุปเบิกใช้วัสดุ - %s × บัญชีค่าใช้จ่าย (มูลค่า)" % title, f_title)
            ws.write(1, 0, sub)
            hr = 3
            heads = [first_head] + ["%s %s" % (c[1], c[2]) for c in cols] + ["รวม", "ใบเบิกใช้ (CONS)", "ส่งขายราคา 0"]
            for c, h in enumerate(heads):
                ws.write(hr, c, h, f_head)
                ws.set_column(c, c, 30 if c == 0 else 14)
            ws.set_row(hr, 40)
            ws.freeze_panes(hr + 1, 1)
            r = hr + 1
            for row in self.matrix(row_field):
                ws.write(r, 0, row["label"], f_text)
                for i, c in enumerate(cols):
                    ws.write_number(r, 1 + i, row["cells"].get(c[0], 0.0), f_num)
                ws.write_number(r, 1 + len(cols), row["total"], f_tot)
                ws.write_number(r, 2 + len(cols), row["cons"], f_num)
                ws.write_number(r, 3 + len(cols), row["legacy"], f_num)
                r += 1
            ct = self.column_totals()
            ws.write(r, 0, "รวม", f_tot)
            for i, c in enumerate(cols):
                ws.write_number(r, 1 + i, ct.get(c[0], 0.0), f_tot)
            ws.write_number(r, 1 + len(cols), self.grand_total(), f_tot)
            st = self.source_totals()
            ws.write_number(r, 2 + len(cols), st["cons"], f_tot)
            ws.write_number(r, 3 + len(cols), st["legacy"], f_tot)

        matrix_sheet("สาขา", "warehouse_id", "สาขา")
        matrix_sheet("หมวดสินค้า", "categ_id", "หมวดสินค้า")

        # เดือน × สาขา
        ws = wb.add_worksheet("เดือน")
        ws.write(0, 0, "สรุปเบิกใช้วัสดุ - เดือน × สาขา (มูลค่า)", f_title)
        ws.write(1, 0, sub)
        months = sorted(set(lines.mapped("month")))
        whs = sorted(set(lines.mapped("warehouse_id")), key=lambda w: w.name or "")
        hr = 3
        ws.write(hr, 0, "สาขา", f_head)
        ws.set_column(0, 0, 16)
        for i, m in enumerate(months):
            ws.write(hr, 1 + i, m, f_head)
            ws.set_column(1 + i, 1 + i, 13)
        ws.write(hr, 1 + len(months), "รวม", f_head)
        mv = defaultdict(float)
        for l in lines:
            mv[(l.warehouse_id.id, l.month)] += l.value
        r = hr + 1
        for w in whs:
            ws.write(r, 0, w.name, f_text)
            tot = 0.0
            for i, m in enumerate(months):
                v = mv.get((w.id, m), 0.0)
                ws.write_number(r, 1 + i, v, f_num)
                tot += v
            ws.write_number(r, 1 + len(months), tot, f_tot)
            r += 1

        ws = wb.add_worksheet("รายการ")
        ws.write(0, 0, "สรุปเบิกใช้วัสดุ - รายการ (สาขา × สินค้า × แหล่ง × เดือน)", f_title)
        ws.write(1, 0, sub)
        heads = [("สาขา", 12), ("Analytic", 16), ("เดือน", 9), ("แหล่ง", 14), ("บัญชีค่าใช้จ่าย", 10), ("ชื่อบัญชี", 26),
                 ("รหัสสินค้า", 14), ("ชื่อสินค้า", 36), ("หมวด", 22), ("หน่วย", 8), ("จำนวนสุทธิ", 11), ("มูลค่าสุทธิ", 13),
                 ("เบิกคืน (จำนวน)", 11), ("เบิกคืน (มูลค่า)", 13), ("บรรทัด", 8)]
        hr = 3
        for c, (h, wd) in enumerate(heads):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, wd)
        ws.freeze_panes(hr + 1, 4)
        src_label = dict(self.env["stock.consumption.line"]._fields["source"].selection)
        r = hr + 1
        for l in lines:
            ws.write(r, 0, l.warehouse_id.name or "", f_text)
            ws.write(r, 1, l.analytic_account_id.display_name or "", f_text)
            ws.write(r, 2, l.month or "", f_text)
            ws.write(r, 3, src_label.get(l.source, ""), f_text)
            ws.write(r, 4, l.expense_code or "", f_text)
            ws.write(r, 5, l.expense_name or "", f_text)
            ws.write(r, 6, l.default_code or "", f_text)
            ws.write(r, 7, l.product_name or "", f_text)
            ws.write(r, 8, l.categ_id.complete_name or "", f_text)
            ws.write(r, 9, l.uom_id.name or "", f_text)
            ws.write_number(r, 10, l.qty, f_num)
            ws.write_number(r, 11, l.value, f_num)
            ws.write_number(r, 12, l.return_qty, f_num)
            ws.write_number(r, 13, l.return_value, f_num)
            ws.write_number(r, 14, l.move_count, f_text)
            r += 1
        ws.autofilter(hr, 0, max(r - 1, hr), len(heads) - 1)
        wb.close()
        return buf.getvalue()


class StockConsumptionLine(models.TransientModel):
    _name = "stock.consumption.line"
    _description = "สรุปเบิกใช้วัสดุ - รายการ"
    _order = "warehouse_id, expense_code, default_code, month, id"

    wizard_id = fields.Many2one("stock.consumption.wizard", required=True, ondelete="cascade")
    warehouse_id = fields.Many2one("stock.warehouse", "สาขา / คลัง")
    analytic_account_id = fields.Many2one("account.analytic.account", "Analytic สาขา")
    product_id = fields.Many2one("product.product", "สินค้า")
    default_code = fields.Char("รหัสสินค้า")
    product_name = fields.Char("ชื่อสินค้า")
    categ_id = fields.Many2one("product.category", "หมวด")
    uom_id = fields.Many2one("uom.uom", "หน่วย")
    expense_account_id = fields.Many2one("account.account", "บัญชีค่าใช้จ่าย")
    expense_code = fields.Char("รหัสบัญชี")
    expense_name = fields.Char("ชื่อบัญชี")
    source = fields.Selection([("cons", "ใบเบิกใช้ (CONS)"), ("legacy", "ส่งขายราคา 0 (วิธีเดิม)")], string="แหล่ง")
    month = fields.Char("เดือน")
    qty = fields.Float("จำนวนสุทธิ", digits=(16, 2))
    value = fields.Float("มูลค่าสุทธิ", digits=(16, 2))
    return_qty = fields.Float("เบิกคืน (จำนวน)", digits=(16, 2))
    return_value = fields.Float("เบิกคืน (มูลค่า)", digits=(16, 2))
    move_count = fields.Integer("บรรทัด")
    date_from = fields.Date(related="wizard_id.date_from")
    date_to = fields.Date(related="wizard_id.date_to")
