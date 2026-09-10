# -*- coding: utf-8 -*-
"""สต็อกติดลบ (Negative Stock)

โหมด current : ยอดคงเหลือ ณ วันที่ ต่อ (สินค้า, สาขา/ตำแหน่ง) จาก stock.move.line done (กติกาเดียวกับ Stock Card)
               เฉพาะที่ < 0 → หาว่าติดลบตั้งแต่รายการไหน (ครั้งล่าสุดที่ยอดข้ามจาก >= 0 ไป < 0)
               + ของค้างรับ (stock.move ยังไม่ done ที่ปลายทางเป็นคลังนั้น) + คำแนะนำ
โหมด events  : ทุกรายการจ่ายออกในช่วงวันที่ ที่ทำให้ยอดหลังจ่าย < 0 (แม้ตอนนี้จะแก้แล้ว)
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

KIND_OUT = {
    "supplier": "ส่งคืนผู้ขาย",
    "customer": "ส่งขาย",
    "internal": "โอนออก",
    "inventory": "ปรับปรุงสต็อก (ลด)",
    "production": "เบิกใช้ / เข้าผลิต",
    "transit": "ส่งระหว่างทาง",
    "view": "จ่ายออก",
}
ADVICE = {
    "customer": "ขายก่อนรับของเข้าระบบ: ตรวจว่ามีใบรับ/ใบโอนเข้าสาขาค้างอยู่ไหม ถ้าไม่มีให้ทำใบรับหรือปรับปรุงนับ",
    "internal": "โอนออกเกินยอดที่มี: ตรวจว่ารับของจาก H.O. เข้าระบบครบไหม (ใบโอนเข้าอาจยัง draft) หรือลงผิดสาขา",
    "production": "เบิกใช้เกินยอด: ของมาถึงแต่ยังไม่บันทึกรับ หรือเบิกผิดสาขา",
    "inventory": "ปรับปรุงนับติดลบ: ยอดนับผิดหรือกรอกเครื่องหมายผิด ให้ตรวจใบปรับปรุงนั้น",
    "supplier": "คืนผู้ขายเกินยอด: ตรวจว่าใบรับสินค้าเดิมบันทึกครบไหม",
}


def thai_date(d):
    if not d:
        return ""
    return "%02d/%02d/%d" % (d.day, d.month, d.year + 543)


class StockNegativeWizard(models.TransientModel):
    _name = "stock.negative.wizard"
    _description = "สต็อกติดลบ"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    mode = fields.Selection(
        [("current", "ติดลบ ณ วันที่"), ("events", "ประวัติรายการที่ทำให้ติดลบ (ช่วงวันที่)")],
        string="โหมด", required=True, default="current",
    )
    date_from = fields.Date("ตั้งแต่วันที่", default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date("ถึงวันที่", required=True, default=fields.Date.context_today)
    warehouse_ids = fields.Many2many("stock.warehouse", string="สาขา / คลัง", help="เว้นว่าง = ทุกสาขาที่มีสิทธิ์เห็น")
    product_ids = fields.Many2many("product.product", string="สินค้า")
    categ_ids = fields.Many2many("product.category", string="หมวดสินค้า")
    split_by_location = fields.Boolean("แยกตำแหน่งในสาขา")
    include_non_storable = fields.Boolean("รวมสินค้าที่ไม่เก็บสต็อก")
    line_ids = fields.One2many("stock.negative.line", "wizard_id")
    line_count = fields.Integer(compute="_compute_line_count")

    @api.depends("mode", "date_from", "date_to")
    def _compute_name(self):
        for w in self:
            if w.mode == "events":
                w.name = "รายการที่ทำให้สต็อกติดลบ %s - %s" % (thai_date(w.date_from), thai_date(w.date_to))
            else:
                w.name = "สต็อกติดลบ ณ %s" % thai_date(w.date_to)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for w in self:
            w.line_count = len(w.line_ids)

    @api.constrains("date_from", "date_to", "mode")
    def _check_dates(self):
        for w in self:
            if w.mode == "events" and w.date_from and w.date_to and w.date_from > w.date_to:
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

    def _local_date(self, dt):
        if not dt:
            return False
        return pytz.utc.localize(dt).astimezone(self._tz()).date()

    # ------------------------------------------------------------------
    # คำนวณ
    # ------------------------------------------------------------------
    def _fetch_rows(self, warehouse_ids, product_ids, end):
        query = """
            SELECT ml.id AS ml_id, ml.date, ml.product_id, ml.quantity_product_uom AS qty,
                   ml.picking_id, ml.reference, ml.location_id AS src_id, ml.location_dest_id AS dst_id,
                   ls.usage AS src_usage, ld.usage AS dst_usage,
                   ls.warehouse_id AS src_wh, ld.warehouse_id AS dst_wh,
                   COALESCE(p.origin, m.origin) AS origin,
                   COALESCE(p.partner_id, m.partner_id) AS partner_id,
                   COALESCE(p.user_id, m.create_uid) AS user_id,
                   svl.unit_cost
              FROM stock_move_line ml
              JOIN stock_move m ON m.id = ml.move_id
              JOIN stock_location ls ON ls.id = ml.location_id
              JOIN stock_location ld ON ld.id = ml.location_dest_id
         LEFT JOIN stock_picking p ON p.id = ml.picking_id
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

    def _fetch_pending_in(self, warehouse_ids, product_ids):
        """ของค้างรับ: stock.move ยังไม่ done ปลายทาง internal ในคลัง → {(product, wh or loc): qty}"""
        self.env.cr.execute(
            """SELECT m.product_id, ld.warehouse_id, m.location_dest_id, m.state, m.reference,
                      COALESCE(SUM(m.product_qty), 0)
                 FROM stock_move m JOIN stock_location ld ON ld.id = m.location_dest_id
                WHERE m.state IN ('draft', 'waiting', 'confirmed', 'partially_available', 'assigned')
                  AND m.company_id = %s AND ld.usage = 'internal' AND ld.warehouse_id = ANY(%s)
                  AND m.product_id = ANY(%s)
             GROUP BY m.product_id, ld.warehouse_id, m.location_dest_id, m.state, m.reference""",
            (self.company_id.id, list(warehouse_ids), list(product_ids)),
        )
        out = defaultdict(lambda: {"qty": 0.0, "refs": []})
        for pid, wh, loc, state, ref, qty in self.env.cr.fetchall():
            key = loc if self.split_by_location else wh
            d = out[(pid, key)]
            d["qty"] += qty
            if ref and ref not in d["refs"]:
                d["refs"].append(ref)
        return out

    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        warehouses = self._get_scope_warehouses()
        products = self._get_scope_products()
        if not products:
            raise UserError(_("ไม่พบสินค้าตามเงื่อนไขที่เลือก"))
        end = self._to_utc(self.date_to + timedelta(days=1))
        start = self._to_utc(self.date_from) if (self.mode == "events" and self.date_from) else None
        split = self.split_by_location
        rows = self._fetch_rows(warehouses.ids, products.ids, end)
        products = products.with_company(self.company_id)
        std_cost = {p.id: p.standard_price or 0.0 for p in products}
        prod_by_id = {p.id: p for p in products}
        wh_scope = set(warehouses.ids)

        entries = defaultdict(list)
        for r in rows:
            src_int = r["src_usage"] == "internal"
            dst_int = r["dst_usage"] == "internal"
            if split:
                if src_int and dst_int and r["src_id"] == r["dst_id"]:
                    continue
                keys_in = [r["dst_id"]] if (dst_int and r["dst_wh"] in wh_scope) else []
                keys_out = [r["src_id"]] if (src_int and r["src_wh"] in wh_scope) else []
            else:
                if src_int and dst_int and r["src_wh"] == r["dst_wh"]:
                    continue
                keys_in = [r["dst_wh"]] if (dst_int and r["dst_wh"] in wh_scope) else []
                keys_out = [r["src_wh"]] if (src_int and r["src_wh"] in wh_scope) else []
            qty = r["qty"] or 0.0
            for k in keys_in:
                entries[(r["product_id"], k)].append((r, qty))
            for k in keys_out:
                entries[(r["product_id"], k)].append((r, -qty))

        loc_ids = {r["src_id"] for r in rows} | {r["dst_id"] for r in rows}
        loc_by_id = {l.id: l for l in self.env["stock.location"].browse(list(loc_ids))}
        wh_by_id = {w.id: w for w in warehouses}
        pending = self._fetch_pending_in(warehouses.ids, products.ids) if self.mode == "current" else {}

        vals = []
        for (pid, key), evs in entries.items():
            product = prod_by_id.get(pid)
            if product is None:
                continue
            rounding = product.uom_id.rounding or 0.001
            if split:
                loc = loc_by_id.get(key)
                wh = loc.warehouse_id if loc is not None else False
                loc_id = key
            else:
                wh = wh_by_id.get(key)
                loc_id = False
            if not wh:
                continue
            cost = std_cost.get(pid, 0.0)
            base = {
                "wizard_id": self.id, "product_id": pid, "default_code": product.default_code or "",
                "product_name": product.name, "categ_id": product.categ_id.id, "uom_id": product.uom_id.id,
                "warehouse_id": wh.id, "location_id": loc_id, "unit_cost": cost,
            }
            bal = 0.0
            neg_since = None  # (row, balance_before) ของรายการที่ทำให้ข้ามไปติดลบครั้งล่าสุด
            for r, q in evs:
                before = bal
                bal += q
                went_neg = q < 0 and before >= -rounding / 2 and bal < -rounding / 2
                if went_neg:
                    neg_since = (r, before)
                elif bal >= -rounding / 2:
                    neg_since = None
                if self.mode == "events" and went_neg and (start is None or r["date"] >= start):
                    vals.append(dict(base, **{
                        "date": r["date"], "reference": r["reference"] or "", "origin": r["origin"] or "",
                        "kind": KIND_OUT.get(r["dst_usage"], ""), "counterpart": self._counterpart(r, loc_by_id, split),
                        "picking_id": r["picking_id"], "user_id": r["user_id"],
                        "qty_before": before, "move_qty": q, "qty": bal, "value": bal * cost,
                        "advice": ADVICE.get(r["dst_usage"], ""),
                    }))
            if self.mode == "current" and bal < -rounding / 2:
                r, before = neg_since if neg_since else (evs[-1][0], 0.0)
                since = self._local_date(r["date"])
                pend = pending.get((pid, key), {"qty": 0.0, "refs": []})
                vals.append(dict(base, **{
                    "qty": bal, "value": bal * cost, "date": r["date"], "neg_since": since,
                    "days_negative": (self.date_to - since).days if since else 0,
                    "reference": r["reference"] or "", "origin": r["origin"] or "",
                    "kind": KIND_OUT.get(r["dst_usage"], ""), "counterpart": self._counterpart(r, loc_by_id, split),
                    "picking_id": r["picking_id"], "user_id": r["user_id"],
                    "qty_before": before, "move_qty": -abs(r["qty"] or 0.0),
                    "pending_in_qty": pend["qty"], "pending_in_refs": ", ".join(pend["refs"][:5]),
                    "covered": pend["qty"] + bal >= -rounding / 2,
                    "advice": ("มีของค้างรับ %s อยู่แล้ว ให้ตรวจรับใบนั้นก่อน" % ", ".join(pend["refs"][:3]))
                    if pend["qty"] > 0 else ADVICE.get(r["dst_usage"], ""),
                }))
        lines = self.env["stock.negative.line"].create(vals)
        _logger.info("stock negative (%s): %d rows -> %d lines", self.mode, len(rows), len(lines))
        return lines

    @staticmethod
    def _counterpart(r, loc_by_id, split):
        other = loc_by_id.get(r["dst_id"])
        if other is None:
            return ""
        if other.usage == "internal" and not split and other.warehouse_id:
            return other.warehouse_id.name
        return other.complete_name or other.name

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
            "type": "ir.actions.act_window", "name": self.name, "res_model": "stock.negative.line",
            "view_mode": "list,form,pivot,graph", "domain": [("wizard_id", "=", self.id)],
            "context": {"group_by": ["warehouse_id"], "mode": self.mode,
                        "split_by_location": self.split_by_location,
                        "create": False, "edit": False, "delete": False},
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._ensure_lines()
        return self.env.ref("custom_stock_negative.action_report_stock_negative").report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self._ensure_lines()
        data = self._build_xlsx(lines)
        attachment = self.env["ir.attachment"].create({
            "name": "NegativeStock_%s_%s.xlsx" % (self.mode, self.date_to.strftime("%Y%m%d")),
            "type": "binary", "datas": base64.b64encode(data), "res_model": self._name, "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url", "url": "/web/content/%d?download=true" % attachment.id, "target": "self"}

    def thai_date(self, d):
        return thai_date(d)

    def local_date(self, dt):
        return thai_date(self._local_date(dt)) if dt else ""

    def warehouse_groups(self):
        self.ensure_one()
        groups = []
        for l in self.line_ids:
            if groups and groups[-1][0] == l.warehouse_id:
                groups[-1][1].append(l)
            else:
                groups.append((l.warehouse_id, [l]))
        return groups

    def kind_summary(self):
        """[(kind, count, value)] เรียงตามจำนวน"""
        agg = defaultdict(lambda: [0, 0.0])
        for l in self.line_ids:
            agg[l.kind or "-"][0] += 1
            agg[l.kind or "-"][1] += l.value
        return sorted(((k, v[0], v[1]) for k, v in agg.items()), key=lambda x: -x[1])

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
        current = self.mode == "current"
        ws = wb.add_worksheet("สต็อกติดลบ" if current else "รายการที่ทำให้ติดลบ")
        ws.write(0, 0, self.name, f_title)
        ws.write(1, 0, "แยกตำแหน่งในสาขา" if self.split_by_location else "สรุปต่อสาขา")
        heads = [("สาขา", 12), ("ตำแหน่ง", 18), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 36), ("หมวด", 20), ("หน่วย", 8),
                 ("ต้นทุน/หน่วย", 11)]
        if current:
            heads += [("ติดลบ (จำนวน)", 11), ("มูลค่า", 13), ("ติดลบตั้งแต่", 11), ("กี่วัน", 7),
                      ("ยอดก่อนรายการ", 11), ("จำนวนรายการ", 11), ("ประเภทรายการ", 14), ("เลขที่เอกสาร", 18),
                      ("อ้างอิง", 18), ("ไป", 20), ("ผู้ทำ", 16), ("ของค้างรับ", 11), ("เอกสารค้างรับ", 24),
                      ("พอแก้ไหม", 8), ("คำแนะนำ", 50)]
        else:
            heads += [("วันที่", 11), ("ประเภทรายการ", 14), ("เลขที่เอกสาร", 18), ("อ้างอิง", 18), ("ไป", 20),
                      ("ผู้ทำ", 16), ("ยอดก่อน", 11), ("จำนวนจ่าย", 11), ("ยอดหลัง", 11), ("มูลค่าติดลบ", 13),
                      ("คำแนะนำ", 50)]
        hr = 3
        for c, (h, w) in enumerate(heads):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, w)
        ws.freeze_panes(hr + 1, 4)
        r = hr + 1
        for l in lines:
            base = [l.warehouse_id.name or "", l.location_id.complete_name if l.location_id else "",
                    l.default_code or "", l.product_name or "", l.categ_id.complete_name or "", l.uom_id.name or ""]
            for c, v in enumerate(base):
                ws.write(r, c, v, f_text)
            ws.write_number(r, 6, l.unit_cost, f_num)
            if current:
                ws.write_number(r, 7, l.qty, f_num)
                ws.write_number(r, 8, l.value, f_num)
                if l.neg_since:
                    ws.write_datetime(r, 9, datetime.combine(l.neg_since, time.min), f_date)
                else:
                    ws.write(r, 9, "", f_text)
                ws.write_number(r, 10, l.days_negative, f_int)
                ws.write_number(r, 11, l.qty_before, f_num)
                ws.write_number(r, 12, l.move_qty, f_num)
                ws.write(r, 13, l.kind or "", f_text)
                ws.write(r, 14, l.reference or "", f_text)
                ws.write(r, 15, l.origin or "", f_text)
                ws.write(r, 16, l.counterpart or "", f_text)
                ws.write(r, 17, l.user_id.name or "", f_text)
                ws.write_number(r, 18, l.pending_in_qty, f_num)
                ws.write(r, 19, l.pending_in_refs or "", f_text)
                ws.write(r, 20, "ใช่" if l.covered else "ไม่", f_text)
                ws.write(r, 21, l.advice or "", f_text)
            else:
                d = self._local_date(l.date)
                ws.write_datetime(r, 7, datetime.combine(d, time.min), f_date)
                ws.write(r, 8, l.kind or "", f_text)
                ws.write(r, 9, l.reference or "", f_text)
                ws.write(r, 10, l.origin or "", f_text)
                ws.write(r, 11, l.counterpart or "", f_text)
                ws.write(r, 12, l.user_id.name or "", f_text)
                ws.write_number(r, 13, l.qty_before, f_num)
                ws.write_number(r, 14, l.move_qty, f_num)
                ws.write_number(r, 15, l.qty, f_num)
                ws.write_number(r, 16, l.value, f_num)
                ws.write(r, 17, l.advice or "", f_text)
            r += 1
        ws.autofilter(hr, 0, max(r - 1, hr), len(heads) - 1)
        wb.close()
        return buf.getvalue()


class StockNegativeLine(models.TransientModel):
    _name = "stock.negative.line"
    _description = "สต็อกติดลบ - รายการ"
    _order = "warehouse_id, location_id, value, date, id"

    wizard_id = fields.Many2one("stock.negative.wizard", required=True, ondelete="cascade")
    name = fields.Char(compute="_compute_name")
    product_id = fields.Many2one("product.product", "สินค้า", required=True)
    default_code = fields.Char("รหัสสินค้า")
    product_name = fields.Char("ชื่อสินค้า")
    categ_id = fields.Many2one("product.category", "หมวด")
    uom_id = fields.Many2one("uom.uom", "หน่วย")
    warehouse_id = fields.Many2one("stock.warehouse", "สาขา / คลัง")
    location_id = fields.Many2one("stock.location", "ตำแหน่ง")
    unit_cost = fields.Float("ต้นทุน/หน่วย", digits=(16, 2))
    qty = fields.Float("ยอดคงเหลือ (ติดลบ)", digits=(16, 2))
    value = fields.Float("มูลค่าติดลบ", digits=(16, 2))
    neg_since = fields.Date("ติดลบตั้งแต่")
    days_negative = fields.Integer("กี่วัน")
    date = fields.Datetime("วันที่รายการ")
    kind = fields.Char("ประเภทรายการ")
    reference = fields.Char("เลขที่เอกสาร")
    origin = fields.Char("อ้างอิง")
    counterpart = fields.Char("ไป")
    picking_id = fields.Many2one("stock.picking", "ใบโอน")
    user_id = fields.Many2one("res.users", "ผู้ทำ")
    qty_before = fields.Float("ยอดก่อนรายการ", digits=(16, 2))
    move_qty = fields.Float("จำนวนรายการ", digits=(16, 2))
    pending_in_qty = fields.Float("ของค้างรับ", digits=(16, 2))
    pending_in_refs = fields.Char("เอกสารค้างรับ")
    covered = fields.Boolean("ของค้างรับพอแก้")
    advice = fields.Char("คำแนะนำ")
    date_to = fields.Date(related="wizard_id.date_to")

    @api.depends("default_code", "product_name", "warehouse_id", "location_id")
    def _compute_name(self):
        for l in self:
            where = l.location_id.complete_name if l.location_id else l.warehouse_id.name
            code = "[%s] " % l.default_code if l.default_code else ""
            l.name = "%s%s - %s" % (code, l.product_name or "", where or "")

    def action_open_picking(self):
        self.ensure_one()
        if not self.picking_id:
            return False
        return {"type": "ir.actions.act_window", "res_model": "stock.picking", "res_id": self.picking_id.id,
                "view_mode": "form", "target": "current"}

    def action_open_pending(self):
        self.ensure_one()
        locs = self.location_id or self.warehouse_id.view_location_id
        return {"type": "ir.actions.act_window", "name": "ของค้างรับ %s" % self.name, "res_model": "stock.move",
                "view_mode": "list,form",
                "domain": [("product_id", "=", self.product_id.id), ("location_dest_id", "child_of", locs.id),
                           ("state", "not in", ("done", "cancel"))],
                "context": {"create": False}}
