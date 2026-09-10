# -*- coding: utf-8 -*-
"""Stock Aging (อายุสินค้าคงคลัง)

หลักการ
-------
* ยอดคงเหลือ ณ วันที่รายงาน ต่อ (สินค้า, สาขา) หรือ (สินค้า, ตำแหน่ง) จาก stock.move.line done
  (กติกาเดียวกับ custom_stock_card: ปลายทาง internal = รับ, ต้นทาง internal = จ่าย, ย้ายภายในคลังเดียวกันไม่นับ)
* ไล่ย้อน "รับเข้า" ของคีย์นั้นจากล่าสุดไปเก่า (FIFO: ของที่จ่ายออกไปคือของเก่า ของที่เหลือคือของใหม่)
  จัดสรรยอดคงเหลือให้การรับแต่ละครั้ง -> อายุ = วันที่รายงาน - วันรับเข้า
* ถ้าไล่รับเข้าจนหมดแล้วยังเหลือ (ประวัติไม่ครบ / เคยติดลบ) เก็บเป็น "ไม่ทราบอายุ"
* มูลค่าชั้นรับเข้า = จำนวนที่จัดสรร x ต้นทุนของ move นั้น (SVL) ถ้าไม่มีใช้ standard_price ปัจจุบัน
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

# ขอบบนของแต่ละช่วง (วัน) ช่วงสุดท้ายคือเกินค่าสุดท้าย
BUCKET_EDGES = [30, 60, 90, 180, 365]
BUCKET_LABELS = ["0-30", "31-60", "61-90", "91-180", "181-365", "เกิน 365"]


def thai_date(d):
    if not d:
        return ""
    return "%02d/%02d/%d" % (d.day, d.month, d.year + 543)


def bucket_index(days):
    for i, edge in enumerate(BUCKET_EDGES):
        if days <= edge:
            return i
    return len(BUCKET_EDGES)


class StockAgingWizard(models.TransientModel):
    _name = "stock.aging.wizard"
    _description = "อายุสินค้าคงคลัง (Stock Aging)"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    date_to = fields.Date("ณ วันที่", required=True, default=fields.Date.context_today)
    warehouse_ids = fields.Many2many(
        "stock.warehouse", string="สาขา / คลัง", help="เว้นว่าง = ทุกสาขาที่มีสิทธิ์เห็น"
    )
    product_ids = fields.Many2many("product.product", string="สินค้า")
    categ_ids = fields.Many2many("product.category", string="หมวดสินค้า")
    split_by_location = fields.Boolean(
        "แยกตำแหน่งในสาขา",
        help="ค่าเริ่มต้นสรุป 1 สาขา = 1 บรรทัดต่อสินค้า ติ๊กเมื่อมีตำแหน่งเก็บย่อยในสาขา",
    )
    include_non_storable = fields.Boolean("รวมสินค้าที่ไม่เก็บสต็อก")
    min_days = fields.Integer(
        "แสดงเฉพาะที่ไม่เคลื่อนไหวเกิน (วัน)", default=0,
        help="0 = แสดงทุกรายการที่มีของคงเหลือ; ใส่เช่น 90 เพื่อดูเฉพาะของนอนเกิน 90 วัน",
    )
    line_ids = fields.One2many("stock.aging.line", "wizard_id")
    line_count = fields.Integer(compute="_compute_line_count")

    @api.depends("date_to")
    def _compute_name(self):
        for w in self:
            w.name = "อายุสินค้าคงคลัง ณ %s" % thai_date(w.date_to)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for w in self:
            w.line_count = len(w.line_ids)

    # ------------------------------------------------------------------
    # ขอบเขต (เหมือน custom_stock_card)
    # ------------------------------------------------------------------
    def _get_scope_warehouses(self):
        self.ensure_one()
        Warehouse = self.env["stock.warehouse"]
        whs = self.warehouse_ids or Warehouse.search(
            [("company_id", "=", self.company_id.id)]
        )
        user = self.env.user
        if (
            "allowed_warehouse_ids" in user._fields
            and user.allowed_warehouse_ids
            and not user.warehouse_unrestricted
        ):
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

    def _get_utc_end(self):
        local = self._tz().localize(
            datetime.combine(self.date_to + timedelta(days=1), time.min)
        )
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _local_date(self, dt):
        if not dt:
            return False
        return pytz.utc.localize(dt).astimezone(self._tz()).date()

    # ------------------------------------------------------------------
    # คำนวณ
    # ------------------------------------------------------------------
    def _fetch_rows(self, warehouse_ids, product_ids, end):
        query = """
            SELECT ml.id            AS ml_id,
                   ml.date          AS date,
                   ml.product_id    AS product_id,
                   ml.quantity_product_uom AS qty,
                   ml.picking_id    AS picking_id,
                   ml.reference     AS reference,
                   ml.location_id   AS src_id,
                   ml.location_dest_id AS dst_id,
                   ls.usage         AS src_usage,
                   ld.usage         AS dst_usage,
                   ls.warehouse_id  AS src_wh,
                   ld.warehouse_id  AS dst_wh,
                   COALESCE(p.origin, m.origin) AS origin,
                   svl.unit_cost    AS unit_cost
              FROM stock_move_line ml
              JOIN stock_move m       ON m.id = ml.move_id
              JOIN stock_location ls  ON ls.id = ml.location_id
              JOIN stock_location ld  ON ld.id = ml.location_dest_id
         LEFT JOIN stock_picking p    ON p.id = ml.picking_id
         LEFT JOIN (
                   SELECT stock_move_id,
                          CASE WHEN SUM(quantity) <> 0
                               THEN SUM(value) / SUM(quantity) END AS unit_cost
                     FROM stock_valuation_layer
                    WHERE stock_move_id IS NOT NULL
                 GROUP BY stock_move_id
                   ) svl ON svl.stock_move_id = m.id
             WHERE ml.state = 'done'
               AND ml.date < %(end)s
               AND m.company_id = %(company)s
               AND (ls.usage = 'internal' OR ld.usage = 'internal')
               AND (ls.warehouse_id = ANY(%(wh)s) OR ld.warehouse_id = ANY(%(wh)s))
               AND ml.product_id = ANY(%(products)s)
          ORDER BY ml.date, ml.id
        """
        self.env.flush_all()
        self.env.cr.execute(
            query,
            {
                "end": end,
                "company": self.company_id.id,
                "wh": list(warehouse_ids),
                "products": list(product_ids),
            },
        )
        return self.env.cr.dictfetchall()

    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()

        warehouses = self._get_scope_warehouses()
        products = self._get_scope_products()
        if not products:
            raise UserError(_("ไม่พบสินค้าตามเงื่อนไขที่เลือก"))
        end = self._get_utc_end()
        split = self.split_by_location
        rows = self._fetch_rows(warehouses.ids, products.ids, end)

        products = products.with_company(self.company_id)
        std_cost = {p.id: p.standard_price or 0.0 for p in products}
        prod_by_id = {p.id: p for p in products}

        # entries[(product, key)] = [(row, signed_qty, cost)] เรียงตามเวลา
        # นับเฉพาะฝั่งที่เป็นสาขาในขอบเขต (ใบโอน H.O.->ATZ ตอนเลือก ATZ ต้องไม่สร้างบรรทัด H.O.)
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
            cost = r["unit_cost"]
            if cost is None:
                cost = std_cost.get(r["product_id"], 0.0)
            cost = abs(cost)
            qty = r["qty"] or 0.0
            for k in keys_in:
                entries[(r["product_id"], k)].append((r, qty, cost))
            for k in keys_out:
                entries[(r["product_id"], k)].append((r, -qty, cost))

        loc_ids = {r["src_id"] for r in rows} | {r["dst_id"] for r in rows}
        loc_by_id = {l.id: l for l in self.env["stock.location"].browse(list(loc_ids))}
        wh_by_id = {w.id: w for w in warehouses}

        Line = self.env["stock.aging.line"]
        Layer = self.env["stock.aging.layer"]
        nb = len(BUCKET_EDGES) + 1
        line_vals, layer_vals = [], []
        for (pid, key), evs in entries.items():
            product = prod_by_id.get(pid)
            if product is None:
                continue
            rounding = product.uom_id.rounding or 0.001
            on_hand = sum(q for _r, q, _c in evs)
            if float_is_zero(on_hand, precision_rounding=rounding):
                continue

            if split:
                loc = loc_by_id.get(key)
                wh = loc.warehouse_id if loc is not None else False
                loc_id = key
            else:
                wh = wh_by_id.get(key)
                loc_id = False
            if not wh:
                continue

            last_in = max((r["date"] for r, q, _c in evs if q > 0), default=None)
            last_out = max((r["date"] for r, q, _c in evs if q < 0), default=None)
            last_move = max(d for d in (last_in, last_out) if d) if (last_in or last_out) else None
            days_no_move = (
                (self.date_to - self._local_date(last_move)).days if last_move else 0
            )
            if self.min_days and days_no_move < self.min_days:
                continue

            b_qty = [0.0] * nb
            b_val = [0.0] * nb
            layers = []
            unknown_qty = 0.0
            oldest_days = 0
            total_val = 0.0
            if on_hand > 0:
                remaining = on_hand
                for r, q, c in reversed(evs):
                    if q <= 0:
                        continue
                    take = min(remaining, q)
                    if float_is_zero(take, precision_rounding=rounding):
                        break
                    rdate = self._local_date(r["date"])
                    days = max((self.date_to - rdate).days, 0)
                    bi = bucket_index(days)
                    b_qty[bi] += take
                    b_val[bi] += take * c
                    total_val += take * c
                    oldest_days = max(oldest_days, days)
                    layers.append(
                        {
                            "date": r["date"],
                            "reference": r["reference"] or "",
                            "origin": r["origin"] or "",
                            "picking_id": r["picking_id"],
                            "source_location_id": r["src_id"],
                            "received_qty": q,
                            "qty": take,
                            "unit_cost": c,
                            "value": take * c,
                            "days": days,
                            "bucket": BUCKET_LABELS[bi],
                        }
                    )
                    remaining -= take
                    if float_is_zero(remaining, precision_rounding=rounding):
                        break
                if remaining > 0 and not float_is_zero(remaining, precision_rounding=rounding):
                    unknown_qty = remaining
                    total_val += remaining * std_cost.get(pid, 0.0)
            else:
                # ยอดติดลบ: ไม่มีอายุ แสดงไว้ให้เห็น
                total_val = on_hand * std_cost.get(pid, 0.0)

            vals = {
                "wizard_id": self.id,
                "product_id": pid,
                "default_code": product.default_code or "",
                "product_name": product.name,
                "categ_id": product.categ_id.id,
                "uom_id": product.uom_id.id,
                "warehouse_id": wh.id,
                "location_id": loc_id,
                "qty": on_hand,
                "value": total_val,
                "unit_cost": (total_val / on_hand) if on_hand else 0.0,
                "unknown_qty": unknown_qty,
                "oldest_days": oldest_days,
                "last_in_date": self._local_date(last_in),
                "last_out_date": self._local_date(last_out),
                "days_no_move": days_no_move,
                "layer_count": len(layers),
            }
            for i in range(nb):
                vals["b%d_qty" % (i + 1)] = b_qty[i]
                vals["b%d_value" % (i + 1)] = b_val[i]
            line_vals.append(vals)
            layer_vals.append(layers)

        lines = Line.create(line_vals)
        flat = []
        for line, layers in zip(lines, layer_vals):
            for l in layers:
                l["line_id"] = line.id
                flat.append(l)
        if flat:
            Layer.create(flat)
        _logger.info(
            "stock aging: %d rows -> %d lines / %d layers", len(rows), len(lines), len(flat)
        )
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
        group = "location_id" if self.split_by_location else "warehouse_id"
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "stock.aging.line",
            "view_mode": "list,form,pivot,graph",
            "domain": [("wizard_id", "=", self.id)],
            "context": {
                "group_by": [group],
                "split_by_location": self.split_by_location,
                "create": False,
                "edit": False,
                "delete": False,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._ensure_lines()
        return self.env.ref(
            "custom_stock_aging.action_report_stock_aging"
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self._ensure_lines()
        data = self._build_xlsx(lines)
        fname = "StockAging_%s.xlsx" % self.date_to.strftime("%Y%m%d")
        attachment = self.env["ir.attachment"].create(
            {
                "name": fname,
                "type": "binary",
                "datas": base64.b64encode(data),
                "res_model": self._name,
                "res_id": self.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%d?download=true" % attachment.id,
            "target": "self",
        }

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------
    def _build_xlsx(self, lines):
        import xlsxwriter

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        f_title = wb.add_format({"bold": True, "font_size": 14})
        f_head = wb.add_format(
            {"bold": True, "bg_color": "#D9E1F2", "border": 1, "align": "center",
             "valign": "vcenter", "text_wrap": True}
        )
        f_text = wb.add_format({"border": 1})
        f_num = wb.add_format({"border": 1, "num_format": "#,##0.00;[Red]-#,##0.00"})
        f_int = wb.add_format({"border": 1, "num_format": "0"})
        f_date = wb.add_format({"border": 1, "num_format": "dd/mm/yyyy"})
        f_tot = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA"})
        f_tot_n = wb.add_format(
            {"border": 1, "bold": True, "bg_color": "#E2EFDA",
             "num_format": "#,##0.00;[Red]-#,##0.00"}
        )
        split = self.split_by_location
        subtitle = "ณ วันที่ %s  |  %s" % (
            self.date_to.strftime("%d/%m/%Y"),
            "แยกตำแหน่งในสาขา" if split else "สรุปต่อสาขา",
        )
        nb = len(BUCKET_LABELS)

        # ---------- sheet 1: สรุป ----------
        ws = wb.add_worksheet("อายุสินค้า")
        ws.write(0, 0, "อายุสินค้าคงคลัง (Stock Aging)", f_title)
        ws.write(1, 0, subtitle)
        heads = [
            ("สาขา", 12), ("ตำแหน่ง", 20), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 38),
            ("หมวด", 20), ("หน่วย", 8), ("คงเหลือ", 11), ("ต้นทุน/หน่วย", 11), ("มูลค่า", 13),
        ]
        heads += [("%s วัน (จำนวน)" % b, 11) for b in BUCKET_LABELS]
        heads += [("%s วัน (มูลค่า)" % b, 13) for b in BUCKET_LABELS]
        heads += [
            ("ไม่ทราบอายุ (จำนวน)", 11), ("อายุเก่าสุด (วัน)", 10),
            ("รับเข้าล่าสุด", 11), ("จ่ายออกล่าสุด", 11), ("ไม่เคลื่อนไหว (วัน)", 11),
        ]
        hr = 3
        for c, (h, w) in enumerate(heads):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, w)
        ws.set_row(hr, 30)
        ws.freeze_panes(hr + 1, 4)
        r = hr + 1
        for l in lines:
            ws.write(r, 0, l.warehouse_id.name or "", f_text)
            ws.write(r, 1, l.location_id.complete_name if l.location_id else "", f_text)
            ws.write(r, 2, l.default_code or "", f_text)
            ws.write(r, 3, l.product_name or "", f_text)
            ws.write(r, 4, l.categ_id.complete_name or "", f_text)
            ws.write(r, 5, l.uom_id.name or "", f_text)
            ws.write_number(r, 6, l.qty, f_num)
            ws.write_number(r, 7, l.unit_cost, f_num)
            ws.write_number(r, 8, l.value, f_num)
            c = 9
            for i in range(nb):
                ws.write_number(r, c + i, l["b%d_qty" % (i + 1)], f_num)
            c += nb
            for i in range(nb):
                ws.write_number(r, c + i, l["b%d_value" % (i + 1)], f_num)
            c += nb
            ws.write_number(r, c, l.unknown_qty, f_num)
            ws.write_number(r, c + 1, l.oldest_days, f_int)
            if l.last_in_date:
                ws.write_datetime(r, c + 2, datetime.combine(l.last_in_date, time.min), f_date)
            else:
                ws.write(r, c + 2, "", f_text)
            if l.last_out_date:
                ws.write_datetime(r, c + 3, datetime.combine(l.last_out_date, time.min), f_date)
            else:
                ws.write(r, c + 3, "", f_text)
            ws.write_number(r, c + 4, l.days_no_move, f_int)
            r += 1
        if lines:
            first, last = hr + 2, r
            ws.write(r, 0, "รวม", f_tot)
            for c in range(1, len(heads)):
                ws.write(r, c, "", f_tot)
            for c in [8] + list(range(9 + nb, 9 + 2 * nb)):
                col = xlsxwriter.utility.xl_col_to_name(c)
                ws.write_formula(r, c, "=SUM(%s%d:%s%d)" % (col, first, col, last), f_tot_n)
        ws.autofilter(hr, 0, max(r - 1, hr), len(heads) - 1)

        # ---------- sheet 2: ชั้นรับเข้า ----------
        wd = wb.add_worksheet("ที่มาของคงเหลือ")
        wd.write(0, 0, "อายุสินค้าคงคลัง - ของคงเหลือมาจากการรับเข้าครั้งไหน", f_title)
        wd.write(1, 0, subtitle)
        dheads = [
            ("สาขา", 12), ("ตำแหน่ง", 20), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 36), ("หน่วย", 8),
            ("วันรับเข้า", 11), ("เลขที่เอกสาร", 18), ("อ้างอิง", 18), ("รับจาก", 24),
            ("รับเข้าทั้งหมด", 11), ("ที่ยังเหลือ", 11), ("ต้นทุน/หน่วย", 11), ("มูลค่า", 13),
            ("อายุ (วัน)", 9), ("ช่วง", 9),
        ]
        for c, (h, w) in enumerate(dheads):
            wd.write(hr, c, h, f_head)
            wd.set_column(c, c, w)
        wd.freeze_panes(hr + 1, 0)
        r = hr + 1
        for l in lines:
            for ly in l.layer_ids:
                wd.write(r, 0, l.warehouse_id.name or "", f_text)
                wd.write(r, 1, l.location_id.complete_name if l.location_id else "", f_text)
                wd.write(r, 2, l.default_code or "", f_text)
                wd.write(r, 3, l.product_name or "", f_text)
                wd.write(r, 4, l.uom_id.name or "", f_text)
                d = self._local_date(ly.date)
                wd.write_datetime(r, 5, datetime.combine(d, time.min), f_date)
                wd.write(r, 6, ly.reference or "", f_text)
                wd.write(r, 7, ly.origin or "", f_text)
                wd.write(r, 8, ly.source_location_id.complete_name or "", f_text)
                wd.write_number(r, 9, ly.received_qty, f_num)
                wd.write_number(r, 10, ly.qty, f_num)
                wd.write_number(r, 11, ly.unit_cost, f_num)
                wd.write_number(r, 12, ly.value, f_num)
                wd.write_number(r, 13, ly.days, f_int)
                wd.write(r, 14, ly.bucket, f_text)
                r += 1
        wd.autofilter(hr, 0, max(r - 1, hr), len(dheads) - 1)

        wb.close()
        return buf.getvalue()

    # helper สำหรับ QWeb
    def thai_date(self, d):
        return thai_date(d)

    def bucket_labels(self):
        return BUCKET_LABELS

    def warehouse_groups(self):
        """[(warehouse, lines)] สำหรับ PDF พร้อมยอดรวมต่อสาขา"""
        self.ensure_one()
        groups = []
        for l in self.line_ids:
            if groups and groups[-1][0] == l.warehouse_id:
                groups[-1][1].append(l)
            else:
                groups.append((l.warehouse_id, [l]))
        return groups


class StockAgingLine(models.TransientModel):
    _name = "stock.aging.line"
    _description = "อายุสินค้าคงคลัง - ต่อสินค้า"
    _order = "warehouse_id, location_id, default_code, product_id, id"

    wizard_id = fields.Many2one("stock.aging.wizard", required=True, ondelete="cascade")
    name = fields.Char(compute="_compute_name")
    product_id = fields.Many2one("product.product", "สินค้า", required=True)
    default_code = fields.Char("รหัสสินค้า")
    product_name = fields.Char("ชื่อสินค้า")
    categ_id = fields.Many2one("product.category", "หมวด")
    uom_id = fields.Many2one("uom.uom", "หน่วย")
    warehouse_id = fields.Many2one("stock.warehouse", "สาขา / คลัง")
    location_id = fields.Many2one("stock.location", "ตำแหน่ง")
    qty = fields.Float("คงเหลือ", digits=(16, 2))
    unit_cost = fields.Float("ต้นทุน/หน่วย", digits=(16, 2))
    value = fields.Float("มูลค่า", digits=(16, 2))
    b1_qty = fields.Float("0-30 วัน", digits=(16, 2))
    b2_qty = fields.Float("31-60 วัน", digits=(16, 2))
    b3_qty = fields.Float("61-90 วัน", digits=(16, 2))
    b4_qty = fields.Float("91-180 วัน", digits=(16, 2))
    b5_qty = fields.Float("181-365 วัน", digits=(16, 2))
    b6_qty = fields.Float("เกิน 365 วัน", digits=(16, 2))
    b1_value = fields.Float("มูลค่า 0-30", digits=(16, 2))
    b2_value = fields.Float("มูลค่า 31-60", digits=(16, 2))
    b3_value = fields.Float("มูลค่า 61-90", digits=(16, 2))
    b4_value = fields.Float("มูลค่า 91-180", digits=(16, 2))
    b5_value = fields.Float("มูลค่า 181-365", digits=(16, 2))
    b6_value = fields.Float("มูลค่า เกิน 365", digits=(16, 2))
    unknown_qty = fields.Float("ไม่ทราบอายุ", digits=(16, 2))
    oldest_days = fields.Integer("อายุเก่าสุด (วัน)")
    last_in_date = fields.Date("รับเข้าล่าสุด")
    last_out_date = fields.Date("จ่ายออกล่าสุด")
    days_no_move = fields.Integer("ไม่เคลื่อนไหว (วัน)")
    layer_count = fields.Integer("จำนวนชั้นรับเข้า")
    layer_ids = fields.One2many("stock.aging.layer", "line_id", "ที่มาของคงเหลือ")
    date_to = fields.Date(related="wizard_id.date_to")

    @api.depends("default_code", "product_name", "warehouse_id", "location_id")
    def _compute_name(self):
        for l in self:
            where = l.location_id.complete_name if l.location_id else l.warehouse_id.name
            code = "[%s] " % l.default_code if l.default_code else ""
            l.name = "%s%s - %s" % (code, l.product_name or "", where or "")


class StockAgingLayer(models.TransientModel):
    _name = "stock.aging.layer"
    _description = "อายุสินค้าคงคลัง - ชั้นรับเข้าที่ยังเหลือ"
    _order = "date desc, id"

    line_id = fields.Many2one("stock.aging.line", required=True, ondelete="cascade")
    date = fields.Datetime("วันรับเข้า")
    reference = fields.Char("เลขที่เอกสาร")
    origin = fields.Char("อ้างอิง")
    picking_id = fields.Many2one("stock.picking", "ใบโอน")
    source_location_id = fields.Many2one("stock.location", "รับจาก")
    received_qty = fields.Float("รับเข้าทั้งหมด", digits=(16, 2))
    qty = fields.Float("ที่ยังเหลือ", digits=(16, 2))
    unit_cost = fields.Float("ต้นทุน/หน่วย", digits=(16, 2))
    value = fields.Float("มูลค่า", digits=(16, 2))
    days = fields.Integer("อายุ (วัน)")
    bucket = fields.Char("ช่วง")

    def action_open_picking(self):
        self.ensure_one()
        if not self.picking_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": self.picking_id.id,
            "view_mode": "form",
            "target": "current",
        }
