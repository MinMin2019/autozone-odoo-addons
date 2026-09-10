# -*- coding: utf-8 -*-
"""สินค้าเคลื่อนไหวช้า / ไม่เคลื่อนไหว (Slow-moving / Dead stock)

* ยอดคงเหลือ ณ วันที่ ต่อ (สินค้า, สาขา) จาก stock.move.line done (กติกาเดียวกับ Stock Card)
* "การใช้" = จ่ายออกไปลูกค้า / เบิกใช้-ผลิต / โอนออกไปสาขาอื่น / ระหว่างทาง
  (ไม่นับ คืนผู้ขาย และ ปรับปรุงนับ เพราะไม่ใช่การใช้จริง)
* การใช้ย้อนหลัง 30/90/180/365 วัน นับถึงวันที่รายงาน
* avg_monthly = การใช้ใน lookback_days ÷ (lookback_days/30)
* months_cover = คงเหลือ ÷ avg_monthly (ถ้า avg = 0 และมีของ = ไม่มีกำหนด)
* ชั้น: dead  = มีของ และไม่ได้ใช้เลยเกิน dead_days (หรือไม่เคยใช้และรับเข้ามาเกิน dead_days)
        slow  = มีของ และ months_cover > slow_months
        normal = ที่เหลือ
* สาขาอื่นที่ยังใช้ใน 90 วัน: top 3 ตามจำนวนใช้ (คำนวณจากชุดข้อมูลเดียวกัน)
"""
import base64
import io
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)

CONSUME_USAGES = ("customer", "production", "internal", "transit")


def thai_date(d):
    if not d:
        return ""
    return "%02d/%02d/%d" % (d.day, d.month, d.year + 543)


class StockSlowMovingWizard(models.TransientModel):
    _name = "stock.slow.moving.wizard"
    _description = "สินค้าเคลื่อนไหวช้า / ไม่เคลื่อนไหว"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_to = fields.Date("ณ วันที่", required=True, default=fields.Date.context_today)
    warehouse_ids = fields.Many2many("stock.warehouse", string="สาขา / คลัง", help="เว้นว่าง = ทุกสาขาที่มีสิทธิ์เห็น")
    product_ids = fields.Many2many("product.product", string="สินค้า")
    categ_ids = fields.Many2many("product.category", string="หมวดสินค้า")
    group_all = fields.Boolean("รวมทุกสาขาเป็นบรรทัดเดียวต่อสินค้า",
                               help="มองภาพรวมบริษัท: โอนระหว่างสาขาในขอบเขตไม่นับเป็นการใช้")
    include_non_storable = fields.Boolean("รวมสินค้าที่ไม่เก็บสต็อก")
    dead_days = fields.Integer("Dead = ไม่ได้ใช้เกิน (วัน)", default=180, required=True)
    slow_months = fields.Float("Slow = พอใช้เกิน (เดือน)", default=6.0, required=True)
    lookback_days = fields.Integer("คิดค่าเฉลี่ยจากย้อนหลัง (วัน)", default=365, required=True)
    only_flagged = fields.Boolean("แสดงเฉพาะ Dead / Slow", default=True)
    effective_days = fields.Integer("วันที่มีข้อมูลจริงที่ใช้คิดค่าเฉลี่ย", readonly=True)
    line_ids = fields.One2many("stock.slow.moving.line", "wizard_id")
    line_count = fields.Integer(compute="_compute_line_count")

    @api.depends("date_to")
    def _compute_name(self):
        for w in self:
            w.name = "สินค้าเคลื่อนไหวช้า ณ %s" % thai_date(w.date_to)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for w in self:
            w.line_count = len(w.line_ids)

    @api.constrains("dead_days", "slow_months", "lookback_days")
    def _check_params(self):
        for w in self:
            if w.dead_days <= 0 or w.slow_months <= 0 or w.lookback_days <= 0:
                raise UserError(_("เกณฑ์ต้องมากกว่า 0"))

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

    def _local_date(self, dt):
        if not dt:
            return False
        return pytz.utc.localize(dt).astimezone(self._tz()).date()

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
    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        warehouses = self._get_scope_warehouses()
        products = self._get_scope_products()
        if not products:
            raise UserError(_("ไม่พบสินค้าตามเงื่อนไขที่เลือก"))
        end = self._to_utc(self.date_to + timedelta(days=1))
        # ดึงข้อมูลทุกสาขาที่มีสิทธิ์เห็น (ไม่ใช่แค่ที่เลือก) เพื่อให้ "สาขาที่ยังใช้" มองข้ามสาขาได้
        all_whs = self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)])
        user = self.env.user
        if "allowed_warehouse_ids" in user._fields and user.allowed_warehouse_ids and not user.warehouse_unrestricted:
            all_whs = all_whs & user.allowed_warehouse_ids
        all_whs |= warehouses
        rows = self._fetch_rows(all_whs.ids, products.ids, end)
        products = products.with_company(self.company_id)
        std_cost = {p.id: p.standard_price or 0.0 for p in products}
        prod_by_id = {p.id: p for p in products}
        wh_scope = set(warehouses.ids)
        wh_all = set(all_whs.ids)
        wh_by_id = {w.id: w for w in all_whs}
        group_all = self.group_all

        # cutoffs (UTC datetime)
        cut = {d: self._to_utc(self.date_to - timedelta(days=d - 1)) for d in (30, 90, 180, 365)}
        cut_lb = self._to_utc(self.date_to - timedelta(days=self.lookback_days - 1))
        cut_90 = cut[90]

        # data[(pid, key)] = dict
        data = defaultdict(lambda: {"bal": 0.0, "last_in": None, "last_out": None, "first_in": None,
                                    "use": {30: 0.0, 90: 0.0, 180: 0.0, 365: 0.0}, "use_lb": 0.0})
        # การใช้ 90 วันต่อสาขา (ไว้หาสาขาที่ยังใช้) — ระดับสาขาเสมอ
        use90_wh = defaultdict(float)  # (pid, wh) -> qty

        for r in rows:
            src_int = r["src_usage"] == "internal"
            dst_int = r["dst_usage"] == "internal"
            src_in = src_int and r["src_wh"] in wh_scope
            dst_in = dst_int and r["dst_wh"] in wh_scope
            qty = r["qty"] or 0.0
            pid = r["product_id"]
            # --- ระดับสาขา ทุกสาขาที่เห็น (สำหรับ "สาขาที่ยังใช้") ---
            if src_int and r["src_wh"] in wh_all and not (dst_int and r["src_wh"] == r["dst_wh"]) \
                    and r["dst_usage"] in CONSUME_USAGES and r["date"] >= cut_90:
                use90_wh[(pid, r["src_wh"])] += qty
            # --- คีย์ของรายงาน ---
            if group_all:
                if src_in and dst_in:
                    continue  # โอนระหว่างสาขาในขอบเขต ไม่ใช่การใช้
                keys_in = [0] if dst_in else []
                keys_out = [0] if src_in else []
            else:
                if src_int and dst_int and r["src_wh"] == r["dst_wh"]:
                    continue
                keys_in = [r["dst_wh"]] if dst_in else []
                keys_out = [r["src_wh"]] if src_in else []
            for k in keys_in:
                d = data[(pid, k)]
                d["bal"] += qty
                d["last_in"] = r["date"]
                if d["first_in"] is None:
                    d["first_in"] = r["date"]
            for k in keys_out:
                d = data[(pid, k)]
                d["bal"] -= qty
                if r["dst_usage"] in CONSUME_USAGES:
                    d["last_out"] = r["date"]
                    for days, c in cut.items():
                        if r["date"] >= c:
                            d["use"][days] += qty
                    if r["date"] >= cut_lb:
                        d["use_lb"] += qty

        # สาขาที่ยังใช้: top 3 ต่อสินค้า
        users_by_pid = defaultdict(list)
        for (pid, wh), q in use90_wh.items():
            if q > 0:
                users_by_pid[pid].append((wh, q))

        # ถ้าข้อมูลมีน้อยกว่าช่วงย้อนหลัง (เช่น go-live ไม่ถึงปี) ให้หารด้วยจำนวนวันที่มีข้อมูลจริง
        # วันแรกที่มีการเคลื่อนไหวจริงจัง (>= 20 บรรทัด/วัน) กันข้อมูลหลงจากปีเก่า ๆ
        per_day = defaultdict(int)
        for r in rows:
            per_day[self._local_date(r["date"])] += 1
        busy = sorted(d for d, n in per_day.items() if n >= 20)
        first_dt = busy[0] if busy else (self._local_date(rows[0]["date"]) if rows else None)
        data_days = (self.date_to - first_dt).days + 1 if first_dt else self.lookback_days
        eff_days = max(1, min(self.lookback_days, data_days))
        months_lb = eff_days / 30.0
        self.effective_days = eff_days
        vals = []
        for (pid, key), d in data.items():
            product = prod_by_id.get(pid)
            if product is None:
                continue
            rounding = product.uom_id.rounding or 0.001
            bal = d["bal"]
            if bal <= rounding / 2:
                continue  # ไม่มีของ (หรือติดลบ) ไม่ใช่เรื่องของรายงานนี้
            cost = std_cost.get(pid, 0.0)
            last_out = self._local_date(d["last_out"])
            last_in = self._local_date(d["last_in"])
            first_in = self._local_date(d["first_in"])
            if last_out:
                days_no_use = (self.date_to - last_out).days
            elif first_in:
                days_no_use = (self.date_to - first_in).days
            else:
                days_no_use = 0
            avg_m = d["use_lb"] / months_lb if months_lb else 0.0
            cover = (bal / avg_m) if avg_m > 0 else 0.0
            if days_no_use >= self.dead_days:
                cls = "dead"
            elif avg_m <= 0 or cover > self.slow_months:
                cls = "slow"
            else:
                cls = "normal"
            if self.only_flagged and cls == "normal":
                continue
            wh_id = False if group_all else key
            others = sorted(((wh, q) for wh, q in users_by_pid.get(pid, []) if wh != key),
                            key=lambda x: -x[1])[:3]
            others_txt = ", ".join("%s (%s)" % (wh_by_id[wh].name, ("%.0f" % q) if q == int(q) else ("%.2f" % q))
                                   for wh, q in others if wh in wh_by_id)
            vals.append({
                "wizard_id": self.id, "product_id": pid, "default_code": product.default_code or "",
                "product_name": product.name, "categ_id": product.categ_id.id, "uom_id": product.uom_id.id,
                "warehouse_id": wh_id, "qty": bal, "unit_cost": cost, "value": bal * cost,
                "last_in_date": last_in, "last_out_date": last_out, "days_no_use": days_no_use,
                "use_30": d["use"][30], "use_90": d["use"][90], "use_180": d["use"][180], "use_365": d["use"][365],
                "avg_monthly": avg_m, "months_cover": cover, "no_usage": avg_m <= 0,
                "classification": cls, "other_users": others_txt,
                "action_hint": self._hint(cls, others_txt, avg_m),
            })
        lines = self.env["stock.slow.moving.line"].create(vals)
        _logger.info("slow moving: %d rows -> %d lines", len(rows), len(lines))
        return lines

    @staticmethod
    def _hint(cls, others, avg_m):
        if cls == "normal":
            return ""
        if others:
            return "โยกไปสาขาที่ยังใช้: %s" % others
        if cls == "dead":
            return "ไม่มีสาขาไหนใช้ใน 90 วัน: พิจารณาคืนผู้ขาย / ลดราคา / ตัดจำหน่าย"
        return "ใช้ช้า: หยุดสั่งซื้อเพิ่มจนกว่าคงเหลือจะลด"

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
            "type": "ir.actions.act_window", "name": self.name, "res_model": "stock.slow.moving.line",
            "view_mode": "list,form,pivot,graph", "domain": [("wizard_id", "=", self.id)],
            "context": {"group_by": ["classification"] if self.group_all else ["warehouse_id", "classification"],
                        "group_all": self.group_all, "create": False, "edit": False, "delete": False},
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._ensure_lines()
        return self.env.ref("custom_stock_slow_moving.action_report_stock_slow_moving").report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self._ensure_lines()
        data = self._build_xlsx(lines)
        attachment = self.env["ir.attachment"].create({
            "name": "SlowMoving_%s.xlsx" % self.date_to.strftime("%Y%m%d"), "type": "binary",
            "datas": base64.b64encode(data), "res_model": self._name, "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%d?download=true" % attachment.id, "target": "self"}

    def thai_date(self, d):
        return thai_date(d)

    def warehouse_summary(self):
        """[(warehouse or False, lines, {dead:(n,v), slow:(n,v), normal:(n,v), total:(n,v)})]"""
        self.ensure_one()
        groups = []
        for l in self.line_ids:
            if groups and groups[-1][0] == l.warehouse_id:
                groups[-1][1].append(l)
            else:
                groups.append((l.warehouse_id, [l]))
        out = []
        for wh, lines in groups:
            s = {}
            for c in ("dead", "slow", "normal"):
                sub = [l for l in lines if l.classification == c]
                s[c] = (len(sub), sum(l.value for l in sub))
            s["total"] = (len(lines), sum(l.value for l in lines))
            out.append((wh, lines, s))
        return out

    def total_summary(self):
        s = {}
        for c in ("dead", "slow", "normal"):
            sub = self.line_ids.filtered(lambda l: l.classification == c)
            s[c] = (len(sub), sum(sub.mapped("value")))
        s["total"] = (len(self.line_ids), sum(self.line_ids.mapped("value")))
        return s

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
        f_int = wb.add_format({"border": 1, "num_format": "0"})
        f_date = wb.add_format({"border": 1, "num_format": "dd/mm/yyyy"})
        f_tot = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA"})
        f_tot_n = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA", "num_format": "#,##0.00"})
        sub = "ณ %s | Dead = ไม่ได้ใช้เกิน %d วัน | Slow = พอใช้เกิน %.1f เดือน | ค่าเฉลี่ยจากย้อนหลัง %d วัน%s" % (
            self.date_to.strftime("%d/%m/%Y"), self.dead_days, self.slow_months, self.lookback_days,
            (" (มีข้อมูลจริง %d วัน)" % self.effective_days if self.effective_days and self.effective_days < self.lookback_days else "")
            + (" | รวมทุกสาขา" if self.group_all else ""))
        cls_label = dict(self.env["stock.slow.moving.line"]._fields["classification"].selection)

        ws = wb.add_worksheet("สรุป")
        ws.write(0, 0, "สินค้าเคลื่อนไหวช้า / ไม่เคลื่อนไหว - สรุป", f_title)
        ws.write(1, 0, sub)
        heads = [("สาขา", 14), ("Dead (รายการ)", 11), ("Dead (มูลค่า)", 14), ("Slow (รายการ)", 11), ("Slow (มูลค่า)", 14),
                 ("Normal (รายการ)", 11), ("Normal (มูลค่า)", 14), ("รวม (รายการ)", 11), ("รวม (มูลค่า)", 14)]
        hr = 3
        for c, (h, w) in enumerate(heads):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, w)
        r = hr + 1
        for wh, _l, s in self.warehouse_summary():
            ws.write(r, 0, wh.name if wh else "ทุกสาขา", f_text)
            c = 1
            for k in ("dead", "slow", "normal", "total"):
                ws.write_number(r, c, s[k][0], f_int)
                ws.write_number(r, c + 1, s[k][1], f_num)
                c += 2
            r += 1
        t = self.total_summary()
        ws.write(r, 0, "รวม", f_tot)
        c = 1
        for k in ("dead", "slow", "normal", "total"):
            ws.write_number(r, c, t[k][0], f_tot)
            ws.write_number(r, c + 1, t[k][1], f_tot_n)
            c += 2

        wd = wb.add_worksheet("รายการ")
        wd.write(0, 0, "สินค้าเคลื่อนไหวช้า / ไม่เคลื่อนไหว - รายการ", f_title)
        wd.write(1, 0, sub)
        dheads = [("สาขา", 12), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 36), ("หมวด", 20), ("หน่วย", 8), ("ชั้น", 8),
                  ("คงเหลือ", 11), ("ต้นทุน/หน่วย", 11), ("มูลค่า", 13), ("รับเข้าล่าสุด", 11), ("ใช้ล่าสุด", 11),
                  ("ไม่ได้ใช้ (วัน)", 10), ("ใช้ 30 วัน", 10), ("ใช้ 90 วัน", 10), ("ใช้ 180 วัน", 10), ("ใช้ 365 วัน", 10),
                  ("เฉลี่ย/เดือน", 10), ("พอใช้ (เดือน)", 10), ("สาขาที่ยังใช้ (90 วัน)", 30), ("คำแนะนำ", 48)]
        for c, (h, w) in enumerate(dheads):
            wd.write(hr, c, h, f_head)
            wd.set_column(c, c, w)
        wd.freeze_panes(hr + 1, 3)
        r = hr + 1
        for l in lines:
            wd.write(r, 0, l.warehouse_id.name if l.warehouse_id else "ทุกสาขา", f_text)
            wd.write(r, 1, l.default_code or "", f_text)
            wd.write(r, 2, l.product_name or "", f_text)
            wd.write(r, 3, l.categ_id.complete_name or "", f_text)
            wd.write(r, 4, l.uom_id.name or "", f_text)
            wd.write(r, 5, cls_label.get(l.classification, ""), f_text)
            wd.write_number(r, 6, l.qty, f_num)
            wd.write_number(r, 7, l.unit_cost, f_num)
            wd.write_number(r, 8, l.value, f_num)
            for c, dt in ((9, l.last_in_date), (10, l.last_out_date)):
                if dt:
                    wd.write_datetime(r, c, datetime.combine(dt, time.min), f_date)
                else:
                    wd.write(r, c, "", f_text)
            wd.write_number(r, 11, l.days_no_use, f_int)
            wd.write_number(r, 12, l.use_30, f_num)
            wd.write_number(r, 13, l.use_90, f_num)
            wd.write_number(r, 14, l.use_180, f_num)
            wd.write_number(r, 15, l.use_365, f_num)
            wd.write_number(r, 16, l.avg_monthly, f_num)
            if l.no_usage:
                wd.write(r, 17, "ไม่มีการใช้", f_text)
            else:
                wd.write_number(r, 17, l.months_cover, f_num)
            wd.write(r, 18, l.other_users or "", f_text)
            wd.write(r, 19, l.action_hint or "", f_text)
            r += 1
        wd.autofilter(hr, 0, max(r - 1, hr), len(dheads) - 1)
        wb.close()
        return buf.getvalue()


class StockSlowMovingLine(models.TransientModel):
    _name = "stock.slow.moving.line"
    _description = "สินค้าเคลื่อนไหวช้า - รายการ"
    _order = "warehouse_id, classification, value desc, id"

    wizard_id = fields.Many2one("stock.slow.moving.wizard", required=True, ondelete="cascade")
    name = fields.Char(compute="_compute_name")
    product_id = fields.Many2one("product.product", "สินค้า", required=True)
    default_code = fields.Char("รหัสสินค้า")
    product_name = fields.Char("ชื่อสินค้า")
    categ_id = fields.Many2one("product.category", "หมวด")
    uom_id = fields.Many2one("uom.uom", "หน่วย")
    warehouse_id = fields.Many2one("stock.warehouse", "สาขา / คลัง")
    classification = fields.Selection([("dead", "Dead"), ("slow", "Slow"), ("normal", "Normal")], string="ชั้น")
    qty = fields.Float("คงเหลือ", digits=(16, 2))
    unit_cost = fields.Float("ต้นทุน/หน่วย", digits=(16, 2))
    value = fields.Float("มูลค่า", digits=(16, 2))
    last_in_date = fields.Date("รับเข้าล่าสุด")
    last_out_date = fields.Date("ใช้ล่าสุด")
    days_no_use = fields.Integer("ไม่ได้ใช้ (วัน)")
    use_30 = fields.Float("ใช้ 30 วัน", digits=(16, 2))
    use_90 = fields.Float("ใช้ 90 วัน", digits=(16, 2))
    use_180 = fields.Float("ใช้ 180 วัน", digits=(16, 2))
    use_365 = fields.Float("ใช้ 365 วัน", digits=(16, 2))
    avg_monthly = fields.Float("เฉลี่ยใช้/เดือน", digits=(16, 2))
    months_cover = fields.Float("พอใช้ (เดือน)", digits=(16, 1))
    no_usage = fields.Boolean("ไม่มีการใช้เลย")
    other_users = fields.Char("สาขาที่ยังใช้ (90 วัน)")
    action_hint = fields.Char("คำแนะนำ")
    date_to = fields.Date(related="wizard_id.date_to")

    @api.depends("default_code", "product_name", "warehouse_id")
    def _compute_name(self):
        for l in self:
            code = "[%s] " % l.default_code if l.default_code else ""
            l.name = "%s%s - %s" % (code, l.product_name or "", l.warehouse_id.name or "ทุกสาขา")

    def action_open_moves(self):
        self.ensure_one()
        domain = [("product_id", "=", self.product_id.id), ("state", "=", "done")]
        if self.warehouse_id:
            loc = self.warehouse_id.view_location_id.id
            domain += ["|", ("location_id", "child_of", loc), ("location_dest_id", "child_of", loc)]
        return {"type": "ir.actions.act_window", "name": self.name, "res_model": "stock.move.line",
                "view_mode": "list,form", "domain": domain, "context": {"create": False, "search_default_done": 1}}
