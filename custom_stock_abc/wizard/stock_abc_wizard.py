# -*- coding: utf-8 -*-
"""ABC Analysis (Pareto)

* เกณฑ์ (basis): usage_value = มูลค่าที่ใช้ไปในช่วง (ค่าเริ่มต้น) / usage_qty = จำนวนที่ใช้ / stock_value = มูลค่าคงเหลือ ณ date_to
* "ใช้ไป" = จ่ายออกไป customer / production / internal(สาขาอื่น) / transit (ไม่นับคืนผู้ขาย/ปรับปรุง)
  ระดับบริษัท: โอนระหว่างสาขาในขอบเขต ไม่นับ
* เรียงมาก→น้อย สะสม % : A ≤ a_pct, B ≤ b_pct, C ที่เหลือ; สินค้าที่เกณฑ์ = 0 → C
* ต่อสาขา (per_warehouse): จัดชั้นแยกภายในแต่ละสาขา
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

CONSUME_USAGES = ("customer", "production", "internal", "transit")


def thai_date(d):
    if not d:
        return ""
    return "%02d/%02d/%d" % (d.day, d.month, d.year + 543)


class StockAbcWizard(models.TransientModel):
    _name = "stock.abc.wizard"
    _description = "ABC Analysis"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_from = fields.Date("ตั้งแต่วันที่", required=True,
                            default=lambda self: fields.Date.context_today(self) - timedelta(days=364))
    date_to = fields.Date("ถึงวันที่", required=True, default=fields.Date.context_today)
    basis = fields.Selection(
        [("usage_value", "มูลค่าที่ใช้ไปในช่วง"), ("usage_qty", "จำนวนที่ใช้ไปในช่วง"), ("stock_value", "มูลค่าคงเหลือ ณ วันสิ้นช่วง")],
        string="เกณฑ์จัดชั้น", default="usage_value", required=True,
    )
    a_pct = fields.Float("A = สะสมถึง (%)", default=80.0, required=True)
    b_pct = fields.Float("B = สะสมถึง (%)", default=95.0, required=True)
    per_warehouse = fields.Boolean("จัดชั้นแยกรายสาขา", help="ปิด = ระดับทั้งบริษัท (โอนระหว่างสาขาไม่นับเป็นการใช้)")
    warehouse_ids = fields.Many2many("stock.warehouse", string="สาขา / คลัง", help="เว้นว่าง = ทุกสาขาที่มีสิทธิ์เห็น")
    product_ids = fields.Many2many("product.product", string="สินค้า")
    categ_ids = fields.Many2many("product.category", string="หมวดสินค้า")
    include_non_storable = fields.Boolean("รวมสินค้าที่ไม่เก็บสต็อก")
    line_ids = fields.One2many("stock.abc.line", "wizard_id")
    line_count = fields.Integer(compute="_compute_line_count")
    saved_date = fields.Date("บันทึกชั้นลงสินค้าเมื่อ", readonly=True)

    @api.depends("date_from", "date_to", "basis")
    def _compute_name(self):
        for w in self:
            w.name = "ABC Analysis %s - %s" % (thai_date(w.date_from), thai_date(w.date_to))

    @api.depends("line_ids")
    def _compute_line_count(self):
        for w in self:
            w.line_count = len(w.line_ids)

    @api.constrains("date_from", "date_to", "a_pct", "b_pct")
    def _check(self):
        for w in self:
            if w.date_from and w.date_to and w.date_from > w.date_to:
                raise UserError(_("วันที่เริ่มต้องไม่เกินวันที่สิ้นสุด"))
            if not (0 < w.a_pct < w.b_pct <= 100):
                raise UserError(_("เกณฑ์ต้องเป็น 0 < A < B <= 100"))

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

    def _tz(self):
        return pytz.timezone(self.env.user.tz or "Asia/Bangkok")

    def _to_utc(self, d):
        return self._tz().localize(datetime.combine(d, time.min)).astimezone(pytz.utc).replace(tzinfo=None)

    def _fetch_rows(self, warehouse_ids, product_ids, end):
        query = """
            SELECT ml.date, ml.product_id, ml.quantity_product_uom AS qty,
                   ls.usage AS src_usage, ld.usage AS dst_usage,
                   ls.warehouse_id AS src_wh, ld.warehouse_id AS dst_wh, svl.unit_cost
              FROM stock_move_line ml
              JOIN stock_move m ON m.id = ml.move_id
              JOIN stock_location ls ON ls.id = ml.location_id
              JOIN stock_location ld ON ld.id = ml.location_dest_id
         LEFT JOIN (SELECT stock_move_id,
                           CASE WHEN SUM(quantity) <> 0 THEN SUM(value) / SUM(quantity) END AS unit_cost
                      FROM stock_valuation_layer WHERE stock_move_id IS NOT NULL GROUP BY stock_move_id) svl
                ON svl.stock_move_id = m.id
             WHERE ml.state = 'done' AND ml.date < %(end)s AND m.company_id = %(company)s
               AND (ls.usage = 'internal' OR ld.usage = 'internal')
               AND (ls.warehouse_id = ANY(%(wh)s) OR ld.warehouse_id = ANY(%(wh)s))
               AND ml.product_id = ANY(%(products)s)
          ORDER BY ml.date, ml.id
        """
        self.env.flush_all()
        self.env.cr.execute(query, {"end": end, "company": self.company_id.id,
                                    "wh": list(warehouse_ids), "products": list(product_ids)})
        return self.env.cr.dictfetchall()

    # ------------------------------------------------------------------
    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        warehouses = self._get_scope_warehouses()
        products = self._get_scope_products()
        if not products:
            raise UserError(_("ไม่พบสินค้าตามเงื่อนไขที่เลือก"))
        start, end = self._to_utc(self.date_from), self._to_utc(self.date_to + timedelta(days=1))
        rows = self._fetch_rows(warehouses.ids, products.ids, end)
        products = products.with_company(self.company_id)
        std_cost = {p.id: p.standard_price or 0.0 for p in products}
        prod_by_id = {p.id: p for p in products}
        wh_scope = set(warehouses.ids)
        per_wh = self.per_warehouse

        # acc[key] = {"use_q","use_v","bal_q","bal_v"}  key = (pid, wh) หรือ (pid, 0)
        acc = defaultdict(lambda: {"use_q": 0.0, "use_v": 0.0, "bal_q": 0.0, "bal_v": 0.0})
        for r in rows:
            src_int = r["src_usage"] == "internal"
            dst_int = r["dst_usage"] == "internal"
            src_in = src_int and r["src_wh"] in wh_scope
            dst_in = dst_int and r["dst_wh"] in wh_scope
            if src_int and dst_int and r["src_wh"] == r["dst_wh"]:
                continue
            if not per_wh and src_in and dst_in:
                continue
            qty = r["qty"] or 0.0
            cost = r["unit_cost"]
            if cost is None:
                cost = std_cost.get(r["product_id"], 0.0)
            cost = abs(cost)
            pid = r["product_id"]
            if dst_in:
                a = acc[(pid, r["dst_wh"] if per_wh else 0)]
                a["bal_q"] += qty
                a["bal_v"] += qty * cost
            if src_in:
                a = acc[(pid, r["src_wh"] if per_wh else 0)]
                a["bal_q"] -= qty
                a["bal_v"] -= qty * cost
                if r["date"] >= start and r["dst_usage"] in CONSUME_USAGES:
                    a["use_q"] += qty
                    a["use_v"] += qty * cost

        # basis value ต่อคีย์
        def basis_of(a, pid):
            if self.basis == "usage_value":
                return a["use_v"]
            if self.basis == "usage_qty":
                return a["use_q"]
            return max(a["bal_q"], 0.0) * std_cost.get(pid, 0.0)

        groups = defaultdict(list)  # wh -> [(pid, basis, a)]
        for (pid, wh), a in acc.items():
            if pid not in prod_by_id:
                continue
            b = basis_of(a, pid)
            if b <= 0 and abs(a["bal_q"]) < 1e-6 and a["use_q"] <= 0:
                continue  # ไม่มีทั้งการใช้และของ
            groups[wh].append((pid, max(b, 0.0), a))

        vals = []
        for wh, items in groups.items():
            items.sort(key=lambda x: -x[1])
            total = sum(x[1] for x in items)
            cum = 0.0
            n = len(items)
            for rank, (pid, b, a) in enumerate(items, start=1):
                cum += b
                cum_pct = (cum / total * 100.0) if total else 100.0
                share = (b / total * 100.0) if total else 0.0
                if b <= 0:
                    cls = "C"
                elif cum_pct <= self.a_pct or (rank == 1):
                    cls = "A"
                elif cum_pct <= self.b_pct:
                    cls = "B"
                else:
                    cls = "C"
                p = prod_by_id[pid]
                vals.append({
                    "wizard_id": self.id, "product_id": pid, "default_code": p.default_code or "",
                    "product_name": p.name, "categ_id": p.categ_id.id, "uom_id": p.uom_id.id,
                    "warehouse_id": wh or False, "rank": rank, "item_count": n,
                    "basis_value": b, "share_pct": share, "cum_pct": cum_pct, "abc_class": cls,
                    "use_qty": a["use_q"], "use_value": a["use_v"],
                    "stock_qty": a["bal_q"], "stock_value": max(a["bal_q"], 0.0) * std_cost.get(pid, 0.0),
                    "unit_cost": std_cost.get(pid, 0.0),
                })
        lines = self.env["stock.abc.line"].create(vals)
        _logger.info("abc analysis: %d rows -> %d lines", len(rows), len(lines))
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
            "type": "ir.actions.act_window", "name": self.name, "res_model": "stock.abc.line",
            "view_mode": "list,form,pivot,graph", "domain": [("wizard_id", "=", self.id)],
            "context": {"group_by": ["warehouse_id", "abc_class"] if self.per_warehouse else ["abc_class"],
                        "per_warehouse": self.per_warehouse, "create": False, "edit": False, "delete": False},
        }

    def action_save_to_products(self):
        """บันทึกชั้น A/B/C ลง product.template (เฉพาะระดับบริษัท)"""
        self.ensure_one()
        if self.per_warehouse:
            raise UserError(_("บันทึกลงสินค้าได้เฉพาะการวิเคราะห์ระดับทั้งบริษัท (ปิด 'จัดชั้นแยกรายสาขา')"))
        lines = self._ensure_lines()
        today = fields.Date.context_today(self)
        by_class = defaultdict(set)
        for l in lines:
            by_class[l.abc_class].add(l.product_id.product_tmpl_id.id)
        Tmpl = self.env["product.template"].with_context(active_test=False)
        for cls, tmpl_ids in by_class.items():
            Tmpl.browse(list(tmpl_ids)).write({"az_abc_class": cls, "az_abc_date": today})
        self.saved_date = today
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("บันทึกชั้น ABC แล้ว"),
                       "message": _("A %d / B %d / C %d สินค้า") % (len(by_class["A"]), len(by_class["B"]), len(by_class["C"])),
                       "type": "success", "sticky": False},
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._ensure_lines()
        return self.env.ref("custom_stock_abc.action_report_stock_abc").report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self._ensure_lines()
        data = self._build_xlsx(lines)
        attachment = self.env["ir.attachment"].create({
            "name": "ABC_%s_%s.xlsx" % (self.date_from.strftime("%Y%m%d"), self.date_to.strftime("%Y%m%d")),
            "type": "binary", "datas": base64.b64encode(data), "res_model": self._name, "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%d?download=true" % attachment.id, "target": "self"}

    def thai_date(self, d):
        return thai_date(d)

    def basis_label(self):
        return dict(self._fields["basis"].selection).get(self.basis, "")

    def pareto(self, warehouse=None):
        """[(class, count, count_pct, value, value_pct)] ต่อกลุ่ม"""
        lines = self.line_ids
        if warehouse is not None:
            lines = lines.filtered(lambda l: l.warehouse_id == warehouse)
        n = len(lines) or 1
        total = sum(lines.mapped("basis_value")) or 1.0
        out = []
        for cls in ("A", "B", "C"):
            sub = lines.filtered(lambda l: l.abc_class == cls)
            v = sum(sub.mapped("basis_value"))
            out.append((cls, len(sub), len(sub) * 100.0 / n, v, v * 100.0 / total))
        return out

    def groups(self):
        """[(warehouse or False, lines)]"""
        if not self.per_warehouse:
            return [(False, self.line_ids)]
        whs = self.line_ids.mapped("warehouse_id").sorted(lambda w: w.name or "")
        return [(w, self.line_ids.filtered(lambda l: l.warehouse_id == w)) for w in whs]

    # ------------------------------------------------------------------
    def _build_xlsx(self, lines):
        import xlsxwriter

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        f_title = wb.add_format({"bold": True, "font_size": 14})
        f_head = wb.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1, "align": "center",
                                "valign": "vcenter", "text_wrap": True})
        f_text = wb.add_format({"border": 1})
        f_num = wb.add_format({"border": 1, "num_format": "#,##0.00;[Red]-#,##0.00"})
        f_pct = wb.add_format({"border": 1, "num_format": "0.00"})
        f_int = wb.add_format({"border": 1, "num_format": "0"})
        f_a = wb.add_format({"border": 1, "bold": True, "bg_color": "#F8CBAD", "align": "center"})
        f_b = wb.add_format({"border": 1, "bold": True, "bg_color": "#FFE699", "align": "center"})
        f_c = wb.add_format({"border": 1, "bg_color": "#E2EFDA", "align": "center"})
        cls_fmt = {"A": f_a, "B": f_b, "C": f_c}
        sub = "%s ถึง %s | เกณฑ์: %s | A ≤ %.0f%% B ≤ %.0f%%%s" % (
            self.date_from.strftime("%d/%m/%Y"), self.date_to.strftime("%d/%m/%Y"), self.basis_label(),
            self.a_pct, self.b_pct, " | แยกรายสาขา" if self.per_warehouse else "")

        ws = wb.add_worksheet("Pareto")
        ws.write(0, 0, "ABC Analysis - สรุป Pareto", f_title)
        ws.write(1, 0, sub)
        heads = [("สาขา", 14), ("ชั้น", 6), ("จำนวนสินค้า", 11), ("% รายการ", 10), ("มูลค่าตามเกณฑ์", 16), ("% มูลค่า", 10)]
        hr = 3
        for c, (h, w) in enumerate(heads):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, w)
        r = hr + 1
        for wh, _l in self.groups():
            for cls, cnt, cpct, v, vpct in self.pareto(wh if self.per_warehouse else None):
                ws.write(r, 0, wh.name if wh else "ทั้งบริษัท", f_text)
                ws.write(r, 1, cls, cls_fmt[cls])
                ws.write_number(r, 2, cnt, f_int)
                ws.write_number(r, 3, cpct, f_pct)
                ws.write_number(r, 4, v, f_num)
                ws.write_number(r, 5, vpct, f_pct)
                r += 1

        wd = wb.add_worksheet("รายการ")
        wd.write(0, 0, "ABC Analysis - รายสินค้า", f_title)
        wd.write(1, 0, sub)
        dheads = [("สาขา", 12), ("อันดับ", 7), ("ชั้น", 6), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 36), ("หมวด", 22), ("หน่วย", 8),
                  ("มูลค่าตามเกณฑ์", 14), ("% ของทั้งหมด", 10), ("สะสม %", 9),
                  ("ใช้ไป (จำนวน)", 11), ("ใช้ไป (มูลค่า)", 13), ("คงเหลือ (จำนวน)", 11), ("คงเหลือ (มูลค่า)", 13), ("ต้นทุน/หน่วย", 11)]
        for c, (h, w) in enumerate(dheads):
            wd.write(hr, c, h, f_head)
            wd.set_column(c, c, w)
        wd.freeze_panes(hr + 1, 5)
        r = hr + 1
        for l in lines.sorted(lambda l: ((l.warehouse_id.name or ""), l.rank)):
            wd.write(r, 0, l.warehouse_id.name if l.warehouse_id else "ทั้งบริษัท", f_text)
            wd.write_number(r, 1, l.rank, f_int)
            wd.write(r, 2, l.abc_class, cls_fmt[l.abc_class])
            wd.write(r, 3, l.default_code or "", f_text)
            wd.write(r, 4, l.product_name or "", f_text)
            wd.write(r, 5, l.categ_id.complete_name or "", f_text)
            wd.write(r, 6, l.uom_id.name or "", f_text)
            wd.write_number(r, 7, l.basis_value, f_num)
            wd.write_number(r, 8, l.share_pct, f_pct)
            wd.write_number(r, 9, l.cum_pct, f_pct)
            wd.write_number(r, 10, l.use_qty, f_num)
            wd.write_number(r, 11, l.use_value, f_num)
            wd.write_number(r, 12, l.stock_qty, f_num)
            wd.write_number(r, 13, l.stock_value, f_num)
            wd.write_number(r, 14, l.unit_cost, f_num)
            r += 1
        wd.autofilter(hr, 0, max(r - 1, hr), len(dheads) - 1)
        wb.close()
        return buf.getvalue()


class StockAbcLine(models.TransientModel):
    _name = "stock.abc.line"
    _description = "ABC Analysis - รายการ"
    _order = "warehouse_id, rank, id"

    wizard_id = fields.Many2one("stock.abc.wizard", required=True, ondelete="cascade")
    name = fields.Char(compute="_compute_name")
    product_id = fields.Many2one("product.product", "สินค้า", required=True)
    default_code = fields.Char("รหัสสินค้า")
    product_name = fields.Char("ชื่อสินค้า")
    categ_id = fields.Many2one("product.category", "หมวด")
    uom_id = fields.Many2one("uom.uom", "หน่วย")
    warehouse_id = fields.Many2one("stock.warehouse", "สาขา / คลัง")
    rank = fields.Integer("อันดับ")
    item_count = fields.Integer("จำนวนสินค้าในกลุ่ม")
    abc_class = fields.Selection([("A", "A"), ("B", "B"), ("C", "C")], string="ชั้น")
    basis_value = fields.Float("มูลค่าตามเกณฑ์", digits=(16, 2))
    share_pct = fields.Float("% ของทั้งหมด", digits=(16, 2))
    cum_pct = fields.Float("สะสม %", digits=(16, 2))
    use_qty = fields.Float("ใช้ไป (จำนวน)", digits=(16, 2))
    use_value = fields.Float("ใช้ไป (มูลค่า)", digits=(16, 2))
    stock_qty = fields.Float("คงเหลือ (จำนวน)", digits=(16, 2))
    stock_value = fields.Float("คงเหลือ (มูลค่า)", digits=(16, 2))
    unit_cost = fields.Float("ต้นทุน/หน่วย", digits=(16, 2))
    date_from = fields.Date(related="wizard_id.date_from")
    date_to = fields.Date(related="wizard_id.date_to")

    @api.depends("default_code", "product_name", "warehouse_id")
    def _compute_name(self):
        for l in self:
            code = "[%s] " % l.default_code if l.default_code else ""
            l.name = "%s%s%s" % (code, l.product_name or "", (" - %s" % l.warehouse_id.name) if l.warehouse_id else "")
