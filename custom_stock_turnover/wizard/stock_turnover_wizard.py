# -*- coding: utf-8 -*-
"""อัตราหมุนเวียนสินค้า (Inventory Turnover / Days of Inventory)

* เหตุการณ์จาก stock.move.line done (กติกาเดียวกับ Stock Card) ต่อ (สินค้า, สาขา)
* มูลค่าต่อบรรทัด = จำนวน x ต้นทุน SVL ของ move (ถ้าไม่มีใช้ standard_price)
* "ใช้ไป" (consumption) = จ่ายออกไป customer / production / internal(สาขาอื่น) / transit
  (คืนผู้ขายและปรับปรุงนับ = "จ่ายอื่น" ไม่นับเป็นการใช้)
* avg_value: simple = (ยกมา + ยกไป)/2 ; monthly = เฉลี่ยของ ยกมา + ยอดสิ้นเดือนทุกเดือนในช่วง
* turnover (รอบ/ปี) = ใช้ไป(มูลค่า) ÷ avg_value x 365/จำนวนวันในช่วง
* days_inventory = 365 ÷ turnover
* คำนวณ 4 ระดับ: company / warehouse / categ / product(x warehouse) โดยรวมจากคีย์ (สินค้า,สาขา)
  - ระดับ company: โอนระหว่างสาขาในขอบเขต ไม่นับเป็นการใช้ (ตัดออกทั้งรับและจ่าย)
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


def month_ends(date_from, date_to):
    """วันสิ้นเดือนทุกเดือนใน [date_from, date_to] (ไม่รวม date_to ถ้าไม่ใช่สิ้นเดือน)"""
    out = []
    d = date_from
    while d <= date_to:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        me = nxt - timedelta(days=1)
        if me <= date_to:
            out.append(me)
        d = nxt
    return out


class StockTurnoverWizard(models.TransientModel):
    _name = "stock.turnover.wizard"
    _description = "อัตราหมุนเวียนสินค้า"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_from = fields.Date("ตั้งแต่วันที่", required=True,
                            default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    date_to = fields.Date("ถึงวันที่", required=True, default=fields.Date.context_today)
    warehouse_ids = fields.Many2many("stock.warehouse", string="สาขา / คลัง", help="เว้นว่าง = ทุกสาขาที่มีสิทธิ์เห็น")
    product_ids = fields.Many2many("product.product", string="สินค้า")
    categ_ids = fields.Many2many("product.category", string="หมวดสินค้า")
    avg_method = fields.Selection(
        [("simple", "(ยกมา + ยกไป) ÷ 2"), ("monthly", "เฉลี่ยยอดสิ้นเดือนทุกเดือนในช่วง")],
        string="วิธีคิดมูลค่าเฉลี่ย", default="monthly", required=True,
    )
    include_non_storable = fields.Boolean("รวมสินค้าที่ไม่เก็บสต็อก")
    line_ids = fields.One2many("stock.turnover.line", "wizard_id")
    line_count = fields.Integer(compute="_compute_line_count")
    period_days = fields.Integer(compute="_compute_period_days")

    @api.depends("date_from", "date_to")
    def _compute_name(self):
        for w in self:
            w.name = "อัตราหมุนเวียนสินค้า %s - %s" % (thai_date(w.date_from), thai_date(w.date_to))

    @api.depends("date_from", "date_to")
    def _compute_period_days(self):
        for w in self:
            w.period_days = (w.date_to - w.date_from).days + 1 if w.date_from and w.date_to else 0

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
    # ขอบเขต (เหมือน custom_stock_card)
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
                   ls.warehouse_id AS src_wh, ld.warehouse_id AS dst_wh,
                   svl.unit_cost
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
    # คำนวณ
    # ------------------------------------------------------------------
    @staticmethod
    def _new_acc():
        return {"open_q": 0.0, "open_v": 0.0, "in_q": 0.0, "in_v": 0.0, "use_q": 0.0, "use_v": 0.0,
                "oth_q": 0.0, "oth_v": 0.0, "points": []}

    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        warehouses = self._get_scope_warehouses()
        products = self._get_scope_products()
        if not products:
            raise UserError(_("ไม่พบสินค้าตามเงื่อนไขที่เลือก"))
        start = self._to_utc(self.date_from)
        end = self._to_utc(self.date_to + timedelta(days=1))
        rows = self._fetch_rows(warehouses.ids, products.ids, end)
        products = products.with_company(self.company_id)
        std_cost = {p.id: p.standard_price or 0.0 for p in products}
        prod_by_id = {p.id: p for p in products}
        wh_scope = set(warehouses.ids)
        wh_by_id = {w.id: w for w in warehouses}
        days = (self.date_to - self.date_from).days + 1
        annual = 365.0 / days if days else 0.0
        # จุดสิ้นเดือน (UTC boundary = เที่ยงคืนของวันถัดไป)
        me_bounds = [self._to_utc(me + timedelta(days=1)) for me in month_ends(self.date_from, self.date_to)]
        if not me_bounds or me_bounds[-1] != end:
            me_bounds.append(end)  # ปลายช่วงเป็นจุดสุดท้ายเสมอ

        # events[(pid, wh)] = [(date, signed_qty, cost, is_use)] ; ระดับ company แยกชุด
        ev_wh = defaultdict(list)
        ev_co = defaultdict(list)
        for r in rows:
            src_int = r["src_usage"] == "internal"
            dst_int = r["dst_usage"] == "internal"
            src_in = src_int and r["src_wh"] in wh_scope
            dst_in = dst_int and r["dst_wh"] in wh_scope
            if src_int and dst_int and r["src_wh"] == r["dst_wh"]:
                continue
            qty = r["qty"] or 0.0
            cost = r["unit_cost"]
            if cost is None:
                cost = std_cost.get(r["product_id"], 0.0)
            cost = abs(cost)
            pid = r["product_id"]
            is_use_out = r["dst_usage"] in CONSUME_USAGES
            if dst_in:
                ev_wh[(pid, r["dst_wh"])].append((r["date"], qty, cost, False))
            if src_in:
                ev_wh[(pid, r["src_wh"])].append((r["date"], -qty, cost, is_use_out))
            # company level: โอนระหว่างสาขาในขอบเขต ตัดออก
            if src_in and dst_in:
                continue
            if dst_in:
                ev_co[pid].append((r["date"], qty, cost, False))
            if src_in:
                ev_co[pid].append((r["date"], -qty, cost, is_use_out))

        def accumulate(evs):
            a = self._new_acc()
            bal_q = bal_v = 0.0
            bi = 0
            pts = []
            for d, q, c, is_use in evs:
                # ปิดจุดสิ้นเดือนที่ผ่านไปแล้ว
                while bi < len(me_bounds) and d >= me_bounds[bi]:
                    pts.append(bal_v)
                    bi += 1
                v = q * c
                if d < start:
                    a["open_q"] += q
                    a["open_v"] += v
                elif q >= 0:
                    a["in_q"] += q
                    a["in_v"] += v
                elif is_use:
                    a["use_q"] += -q
                    a["use_v"] += -v
                else:
                    a["oth_q"] += -q
                    a["oth_v"] += -v
                bal_q += q
                bal_v += v
            while bi < len(me_bounds):
                pts.append(bal_v)
                bi += 1
            a["close_q"] = bal_q
            a["close_v"] = bal_v
            a["points"] = pts  # ยอด ณ สิ้นเดือนแต่ละเดือน (ตัวสุดท้าย = ยกไป)
            return a

        def finish(a):
            if self.avg_method == "monthly":
                pts = [a["open_v"]] + a["points"]
                avg = sum(pts) / len(pts) if pts else 0.0
            else:
                avg = (a["open_v"] + a["close_v"]) / 2.0
            turnover = (a["use_v"] / avg * annual) if avg > 0.005 else 0.0
            dio = (365.0 / turnover) if turnover > 0 else 0.0
            a["avg_v"] = avg
            a["turnover"] = turnover
            a["dio"] = dio
            return a

        def add_into(dst, a):
            for k in ("open_q", "open_v", "in_q", "in_v", "use_q", "use_v", "oth_q", "oth_v", "close_q", "close_v"):
                dst[k] = dst.get(k, 0.0) + a[k]
            if "points" not in dst or not dst["points"]:
                dst["points"] = list(a["points"])
            else:
                dst["points"] = [x + y for x, y in zip(dst["points"], a["points"])]

        # ระดับ product×warehouse → รวมขึ้น warehouse / categ
        prod_lines = {}
        wh_agg = defaultdict(dict)
        cat_agg = defaultdict(dict)
        for (pid, wh), evs in ev_wh.items():
            product = prod_by_id.get(pid)
            if product is None:
                continue
            a = accumulate(evs)
            prod_lines[(pid, wh)] = a
            add_into(wh_agg[wh], a)
            add_into(cat_agg[product.categ_id.id], a)
        co_agg = {}
        for pid, evs in ev_co.items():
            add_into(co_agg, accumulate(evs))

        vals = []

        def line_vals(level, a, **extra):
            a = finish(a)
            v = {"wizard_id": self.id, "level": level,
                 "opening_qty": a["open_q"], "opening_value": a["open_v"], "in_qty": a["in_q"], "in_value": a["in_v"],
                 "use_qty": a["use_q"], "use_value": a["use_v"], "other_out_qty": a["oth_q"], "other_out_value": a["oth_v"],
                 "closing_qty": a["close_q"], "closing_value": a["close_v"], "avg_value": a["avg_v"],
                 "turnover": a["turnover"], "days_inventory": a["dio"]}
            v.update(extra)
            return v

        if co_agg:
            vals.append(line_vals("company", co_agg, name="ทั้งบริษัท (ไม่นับโอนระหว่างสาขา)"))
        for wh, a in wh_agg.items():
            w = wh_by_id.get(wh)
            vals.append(line_vals("warehouse", a, warehouse_id=wh, name=w.name if w else str(wh)))
        Categ = self.env["product.category"].with_context(active_test=False)
        for cid, a in cat_agg.items():
            c = Categ.browse(cid)
            vals.append(line_vals("categ", a, categ_id=cid, name=c.complete_name))
        for (pid, wh), a in prod_lines.items():
            p = prod_by_id[pid]
            if all(abs(a[k]) < 0.005 for k in ("open_v", "close_v", "use_v", "in_v", "open_q", "close_q", "use_q", "in_q")):
                continue
            vals.append(line_vals("product", a, warehouse_id=wh, product_id=pid, categ_id=p.categ_id.id,
                                  default_code=p.default_code or "", uom_id=p.uom_id.id,
                                  name="%s%s" % (("[%s] " % p.default_code) if p.default_code else "", p.name)))
        lines = self.env["stock.turnover.line"].create(vals)
        _logger.info("stock turnover: %d rows -> %d lines", len(rows), len(lines))
        return lines

    def _ensure_lines(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_compute()
        return self.line_ids

    # ------------------------------------------------------------------
    # ปุ่ม
    # ------------------------------------------------------------------
    def action_view(self):
        self.ensure_one()
        self.action_compute()
        return {
            "type": "ir.actions.act_window", "name": self.name, "res_model": "stock.turnover.line",
            "view_mode": "list,form,pivot,graph", "domain": [("wizard_id", "=", self.id)],
            "context": {"search_default_level_warehouse": 1, "create": False, "edit": False, "delete": False},
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._ensure_lines()
        return self.env.ref("custom_stock_turnover.action_report_stock_turnover").report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self._ensure_lines()
        data = self._build_xlsx(lines)
        attachment = self.env["ir.attachment"].create({
            "name": "Turnover_%s_%s.xlsx" % (self.date_from.strftime("%Y%m%d"), self.date_to.strftime("%Y%m%d")),
            "type": "binary", "datas": base64.b64encode(data), "res_model": self._name, "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%d?download=true" % attachment.id, "target": "self"}

    def thai_date(self, d):
        return thai_date(d)

    def avg_method_label(self):
        return dict(self._fields["avg_method"].selection).get(self.avg_method, "")

    def lines_of(self, level):
        return self.line_ids.filtered(lambda l: l.level == level)

    # ------------------------------------------------------------------
    # Excel
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
        f_rat = wb.add_format({"border": 1, "num_format": "0.00"})
        f_int = wb.add_format({"border": 1, "num_format": "#,##0"})
        sub = "%s ถึง %s (%d วัน) | มูลค่าเฉลี่ย: %s" % (
            self.date_from.strftime("%d/%m/%Y"), self.date_to.strftime("%d/%m/%Y"), self.period_days,
            self.avg_method_label())
        num_heads = [("ยกมา (มูลค่า)", 14), ("รับ (มูลค่า)", 14), ("ใช้ไป (มูลค่า)", 14), ("จ่ายอื่น (มูลค่า)", 13),
                     ("ยกไป (มูลค่า)", 14), ("มูลค่าเฉลี่ยที่ถือ", 14), ("Turnover (รอบ/ปี)", 12), ("Days of Inventory", 12),
                     ("ยกมา (จำนวน)", 11), ("รับ (จำนวน)", 11), ("ใช้ไป (จำนวน)", 11), ("ยกไป (จำนวน)", 11)]
        num_keys = ["opening_value", "in_value", "use_value", "other_out_value", "closing_value", "avg_value",
                    "turnover", "days_inventory", "opening_qty", "in_qty", "use_qty", "closing_qty"]

        def sheet(title, level, id_heads, id_getter):
            ws = wb.add_worksheet(title)
            ws.write(0, 0, "อัตราหมุนเวียนสินค้า - %s" % title, f_title)
            ws.write(1, 0, sub)
            heads = id_heads + num_heads
            hr = 3
            for c, (h, w) in enumerate(heads):
                ws.write(hr, c, h, f_head)
                ws.set_column(c, c, w)
            ws.set_row(hr, 30)
            ws.freeze_panes(hr + 1, len(id_heads))
            r = hr + 1
            for l in self.lines_of(level).sorted(lambda l: -l.avg_value):
                for c, v in enumerate(id_getter(l)):
                    ws.write(r, c, v, f_text)
                base = len(id_heads)
                for i, k in enumerate(num_keys):
                    fmt = f_rat if k in ("turnover",) else (f_int if k == "days_inventory" else f_num)
                    ws.write_number(r, base + i, l[k], fmt)
                r += 1
            ws.autofilter(hr, 0, max(r - 1, hr), len(heads) - 1)

        sheet("ทั้งบริษัท", "company", [("ระดับ", 30)], lambda l: [l.name])
        sheet("สาขา", "warehouse", [("สาขา", 16)], lambda l: [l.name])
        sheet("หมวด", "categ", [("หมวดสินค้า", 36)], lambda l: [l.name])
        sheet("สินค้า", "product", [("สาขา", 12), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 36), ("หมวด", 22), ("หน่วย", 8)],
              lambda l: [l.warehouse_id.name or "", l.default_code or "", l.product_id.name or "",
                         l.categ_id.complete_name or "", l.uom_id.name or ""])
        wb.close()
        return buf.getvalue()


class StockTurnoverLine(models.TransientModel):
    _name = "stock.turnover.line"
    _description = "อัตราหมุนเวียนสินค้า - รายการ"
    _order = "level, avg_value desc, id"

    wizard_id = fields.Many2one("stock.turnover.wizard", required=True, ondelete="cascade")
    level = fields.Selection([("company", "ทั้งบริษัท"), ("warehouse", "สาขา"), ("categ", "หมวดสินค้า"),
                              ("product", "สินค้า × สาขา")], string="ระดับ", required=True)
    name = fields.Char("รายการ")
    warehouse_id = fields.Many2one("stock.warehouse", "สาขา / คลัง")
    categ_id = fields.Many2one("product.category", "หมวด")
    product_id = fields.Many2one("product.product", "สินค้า")
    default_code = fields.Char("รหัสสินค้า")
    uom_id = fields.Many2one("uom.uom", "หน่วย")
    opening_qty = fields.Float("ยกมา", digits=(16, 2))
    in_qty = fields.Float("รับ", digits=(16, 2))
    use_qty = fields.Float("ใช้ไป", digits=(16, 2))
    other_out_qty = fields.Float("จ่ายอื่น", digits=(16, 2))
    closing_qty = fields.Float("ยกไป", digits=(16, 2))
    opening_value = fields.Float("มูลค่ายกมา", digits=(16, 2))
    in_value = fields.Float("มูลค่ารับ", digits=(16, 2))
    use_value = fields.Float("มูลค่าใช้ไป", digits=(16, 2))
    other_out_value = fields.Float("มูลค่าจ่ายอื่น", digits=(16, 2))
    closing_value = fields.Float("มูลค่ายกไป", digits=(16, 2))
    avg_value = fields.Float("มูลค่าเฉลี่ยที่ถือ", digits=(16, 2))
    turnover = fields.Float("Turnover (รอบ/ปี)", digits=(16, 2))
    days_inventory = fields.Float("Days of Inventory", digits=(16, 0))
    date_from = fields.Date(related="wizard_id.date_from")
    date_to = fields.Date(related="wizard_id.date_to")
