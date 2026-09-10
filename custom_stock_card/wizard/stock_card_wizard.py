# -*- coding: utf-8 -*-
"""บัญชีคุมสินค้า (Stock Card)

หลักการคำนวณ
------------
* อ่านจาก stock.move.line ที่ state = done (จำนวนในหน่วยหลักของสินค้า = quantity_product_uom)
* โหมด "ต่อสาขา" (ค่าเริ่มต้น): ยึด warehouse ของ location ต้นทาง/ปลายทาง
  - ปลายทางเป็น internal ของสาขา A  -> "รับ" ของสาขา A
  - ต้นทางเป็น internal ของสาขา A    -> "จ่าย" ของสาขา A
  - ย้ายภายในสาขาเดียวกัน (internal -> internal คลังเดียวกัน) ไม่นับ
* โหมด "แยกตำแหน่งในสาขา": เหมือนกันแต่ยึดที่ location แทน warehouse
* มูลค่าต่อบรรทัด = จำนวน x ต้นทุน/หน่วย
  - ต้นทุน/หน่วย = ที่ Odoo บันทึกใน stock.valuation.layer ของ move นั้น (sum(value)/sum(quantity))
  - ถ้า move ไม่มี layer (โอนระหว่างสาขา, สินค้าไม่ตีมูลค่า) ใช้ต้นทุนปัจจุบันของสินค้า (standard_price)
* ยอดยกมา = ผลรวมสะสมของทุกบรรทัดก่อนวันเริ่ม, ยอดยกไป = ยกมา + รับ - จ่าย
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

# ป้ายชื่อรายการ ตาม usage ของ location ฝั่งตรงข้าม
KIND_IN = {
    "supplier": "รับซื้อ",
    "customer": "รับคืนจากลูกค้า",
    "internal": "โอนเข้า",
    "inventory": "ปรับปรุงสต็อก (เพิ่ม)",
    "production": "รับจากผลิต / คืนเบิก",
    "transit": "รับจากระหว่างทาง",
    "view": "รับเข้า",
}
KIND_OUT = {
    "supplier": "ส่งคืนผู้ขาย",
    "customer": "ส่งขาย",
    "internal": "โอนออก",
    "inventory": "ปรับปรุงสต็อก (ลด)",
    "production": "เบิกใช้ / เข้าผลิต",
    "transit": "ส่งระหว่างทาง",
    "view": "จ่ายออก",
}

THAI_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]


def thai_date(d):
    """dd/mm/พ.ศ. สำหรับ PDF"""
    if not d:
        return ""
    return "%02d/%02d/%d" % (d.day, d.month, d.year + 543)


class StockCardWizard(models.TransientModel):
    _name = "stock.card.wizard"
    _description = "บัญชีคุมสินค้า (Stock Card)"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    date_from = fields.Date(
        "ตั้งแต่วันที่", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        "ถึงวันที่", required=True, default=fields.Date.context_today
    )
    warehouse_ids = fields.Many2many(
        "stock.warehouse", string="สาขา / คลัง",
        help="เว้นว่าง = ทุกสาขาที่มีสิทธิ์เห็น",
    )
    product_ids = fields.Many2many(
        "product.product", string="สินค้า",
        help="เว้นว่าง = ทุกสินค้า (ตามหมวดที่เลือก)",
    )
    categ_ids = fields.Many2many("product.category", string="หมวดสินค้า")
    split_by_location = fields.Boolean(
        "แยกตำแหน่งในสาขา",
        help="ค่าเริ่มต้นสรุป 1 สาขา = 1 บรรทัดต่อสินค้า "
        "ติ๊กเมื่อต้องการแยกตามตำแหน่งเก็บย่อยในสาขา (ชั้นวาง/ห้อง)",
    )
    include_non_storable = fields.Boolean(
        "รวมสินค้าที่ไม่เก็บสต็อก",
        help="ปกติแสดงเฉพาะสินค้าที่ติ๊ก Track Inventory "
        "(สินค้าที่ไม่เก็บสต็อกแต่เคยผ่านใบรับจะมียอดค้างหลอก)",
    )
    hide_zero = fields.Boolean(
        "ซ่อนรายการที่ไม่มียอดและไม่มีการเคลื่อนไหว", default=True
    )
    line_ids = fields.One2many("stock.card.line", "wizard_id")
    line_count = fields.Integer(compute="_compute_line_count")

    @api.depends("date_from", "date_to")
    def _compute_name(self):
        for w in self:
            w.name = "บัญชีคุมสินค้า %s - %s" % (
                thai_date(w.date_from), thai_date(w.date_to)
            )

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
    # ขอบเขต
    # ------------------------------------------------------------------
    def _get_scope_warehouses(self):
        """คลังที่ใช้ในรายงาน — เคารพ custom_warehouse_scope ถ้าติดตั้งอยู่"""
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
        """product.product ที่เข้าข่าย (รวม archived เพราะอาจมีประวัติ)"""
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

    def _get_utc_bounds(self):
        """แปลงวันที่ (เขตเวลาผู้ใช้) เป็น datetime UTC: [start, end)"""
        tz = pytz.timezone(self.env.user.tz or "Asia/Bangkok")

        def to_utc(d):
            local = tz.localize(datetime.combine(d, time.min))
            return local.astimezone(pytz.utc).replace(tzinfo=None)

        return to_utc(self.date_from), to_utc(self.date_to + timedelta(days=1))

    # ------------------------------------------------------------------
    # คำนวณ
    # ------------------------------------------------------------------
    def _fetch_rows(self, warehouse_ids, product_ids, end):
        query = """
            SELECT ml.id            AS ml_id,
                   ml.date          AS date,
                   ml.product_id    AS product_id,
                   ml.quantity_product_uom AS qty,
                   ml.move_id       AS move_id,
                   ml.picking_id    AS picking_id,
                   ml.reference     AS reference,
                   ml.location_id   AS src_id,
                   ml.location_dest_id AS dst_id,
                   ls.usage         AS src_usage,
                   ld.usage         AS dst_usage,
                   ls.warehouse_id  AS src_wh,
                   ld.warehouse_id  AS dst_wh,
                   COALESCE(p.origin, m.origin)         AS origin,
                   COALESCE(p.partner_id, m.partner_id) AS partner_id,
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
        """คำนวณใหม่ทั้งชุด (ล้างของเดิมก่อน)"""
        self.ensure_one()
        self.line_ids.unlink()

        warehouses = self._get_scope_warehouses()
        products = self._get_scope_products()
        if not products:
            raise UserError(_("ไม่พบสินค้าตามเงื่อนไขที่เลือก"))
        start, end = self._get_utc_bounds()
        split = self.split_by_location

        rows = self._fetch_rows(warehouses.ids, products.ids, end)

        # ต้นทุนปัจจุบันของสินค้า (fallback เมื่อ move ไม่มี valuation layer)
        products = products.with_company(self.company_id)
        std_cost = {p.id: p.standard_price or 0.0 for p in products}
        prod_by_id = {p.id: p for p in products}
        prec = 6

        # รวมบรรทัดตาม (สินค้า, คีย์) — คีย์ = warehouse id หรือ location id
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

        # ชื่อที่ต้องใช้แสดง
        loc_ids = {r["src_id"] for r in rows} | {r["dst_id"] for r in rows}
        locations = self.env["stock.location"].browse(list(loc_ids))
        loc_by_id = {l.id: l for l in locations}
        partner_ids = {r["partner_id"] for r in rows if r["partner_id"]}
        partners = self.env["res.partner"].browse(list(partner_ids))
        partner_name = {p.id: p.display_name for p in partners}
        wh_by_id = {w.id: w for w in warehouses}
        if not split:
            # โอนเข้ามาจากคลังนอกขอบเขตก็ต้องรู้ชื่อ
            extra_wh = {r["src_wh"] for r in rows} | {r["dst_wh"] for r in rows}
            extra_wh = {w for w in extra_wh if w and w not in wh_by_id}
            for w in self.env["stock.warehouse"].browse(list(extra_wh)):
                wh_by_id[w.id] = w

        def counterpart(r, sign):
            """ฝั่งตรงข้ามของรายการ (ชื่อคู่ค้า หรือชื่อตำแหน่ง/คลัง)"""
            other_id = r["src_id"] if sign > 0 else r["dst_id"]
            other = loc_by_id.get(other_id)
            if other is None:
                return ""
            if other.usage in ("supplier", "customer") and r["partner_id"]:
                return partner_name.get(r["partner_id"], "")
            if other.usage == "internal" and not split and other.warehouse_id:
                return other.warehouse_id.name
            return other.complete_name or other.name

        Line = self.env["stock.card.line"]
        Move = self.env["stock.card.move"]
        line_vals, move_vals = [], []
        for (pid, key), evs in entries.items():
            product = prod_by_id.get(pid)
            if product is None:
                continue
            rounding = product.uom_id.rounding or 0.001
            opening_qty = opening_val = 0.0
            in_range = []
            for r, q, c in evs:
                if r["date"] < start:
                    opening_qty += q
                    opening_val += q * c
                else:
                    in_range.append((r, q, c))
            if self.hide_zero and not in_range and float_is_zero(
                opening_qty, precision_rounding=rounding
            ):
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

            in_qty = out_qty = in_val = out_val = 0.0
            bal_qty, bal_val = opening_qty, opening_val
            moves = []
            for r, q, c in in_range:
                val = q * c
                bal_qty += q
                bal_val += val
                if q >= 0:
                    in_qty += q
                    in_val += val
                else:
                    out_qty += -q
                    out_val += -val
                sign = 1 if q >= 0 else -1
                other_usage = r["src_usage"] if sign > 0 else r["dst_usage"]
                kind = (KIND_IN if sign > 0 else KIND_OUT).get(other_usage, "")
                moves.append(
                    {
                        "date": r["date"],
                        "move_line_id": r["ml_id"],
                        "picking_id": r["picking_id"],
                        "reference": r["reference"] or "",
                        "origin": r["origin"] or "",
                        "partner_id": r["partner_id"],
                        "location_id": r["src_id"],
                        "location_dest_id": r["dst_id"],
                        "kind": kind,
                        "counterpart": counterpart(r, sign),
                        "in_qty": q if q >= 0 else 0.0,
                        "out_qty": -q if q < 0 else 0.0,
                        "balance_qty": bal_qty,
                        "unit_cost": c,
                        "in_value": val if q >= 0 else 0.0,
                        "out_value": -val if q < 0 else 0.0,
                        "balance_value": bal_val,
                    }
                )
            line_vals.append(
                {
                    "wizard_id": self.id,
                    "product_id": pid,
                    "default_code": product.default_code or "",
                    "product_name": product.name,
                    "categ_id": product.categ_id.id,
                    "uom_id": product.uom_id.id,
                    "warehouse_id": wh.id,
                    "location_id": loc_id,
                    "opening_qty": opening_qty,
                    "in_qty": in_qty,
                    "out_qty": out_qty,
                    "closing_qty": bal_qty,
                    "opening_value": opening_val,
                    "in_value": in_val,
                    "out_value": out_val,
                    "closing_value": bal_val,
                    "unit_cost": (bal_val / bal_qty)
                    if not float_is_zero(bal_qty, precision_rounding=rounding)
                    else std_cost.get(pid, 0.0),
                    "move_count": len(moves),
                }
            )
            move_vals.append(moves)

        lines = Line.create(line_vals)
        flat = []
        for line, moves in zip(lines, move_vals):
            for m in moves:
                m["line_id"] = line.id
                flat.append(m)
        if flat:
            Move.create(flat)
        _logger.info(
            "stock card: %d rows -> %d lines / %d moves", len(rows), len(lines), len(flat)
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
            "res_model": "stock.card.line",
            "view_mode": "list,form",
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
            "custom_stock_card.action_report_stock_card"
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self._ensure_lines()
        data = self._build_xlsx(lines)
        fname = "StockCard_%s_%s.xlsx" % (
            self.date_from.strftime("%Y%m%d"), self.date_to.strftime("%Y%m%d")
        )
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
        f_qty = wb.add_format({"border": 1, "num_format": "#,##0.00;[Red]-#,##0.00"})
        f_val = wb.add_format({"border": 1, "num_format": "#,##0.00;[Red]-#,##0.00"})
        f_date = wb.add_format({"border": 1, "num_format": "dd/mm/yyyy"})
        f_open = wb.add_format({"border": 1, "bold": True, "bg_color": "#FFF2CC"})
        f_open_n = wb.add_format(
            {"border": 1, "bold": True, "bg_color": "#FFF2CC",
             "num_format": "#,##0.00;[Red]-#,##0.00"}
        )
        f_tot = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA"})
        f_tot_n = wb.add_format(
            {"border": 1, "bold": True, "bg_color": "#E2EFDA",
             "num_format": "#,##0.00;[Red]-#,##0.00"}
        )
        split = self.split_by_location
        subtitle = "%s ถึง %s  |  %s" % (
            self.date_from.strftime("%d/%m/%Y"),
            self.date_to.strftime("%d/%m/%Y"),
            "แยกตำแหน่งในสาขา" if split else "สรุปต่อสาขา",
        )

        # ---------- sheet 1: สรุป ----------
        ws = wb.add_worksheet("สรุป")
        ws.write(0, 0, "บัญชีคุมสินค้า (Stock Card) - สรุป", f_title)
        ws.write(1, 0, subtitle)
        heads = [
            ("สาขา", 14), ("ตำแหน่ง", 22), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 40),
            ("หมวด", 22), ("หน่วย", 8),
            ("ยกมา (จำนวน)", 12), ("รับ (จำนวน)", 12), ("จ่าย (จำนวน)", 12), ("ยกไป (จำนวน)", 12),
            ("ต้นทุน/หน่วย", 12),
            ("ยกมา (มูลค่า)", 14), ("รับ (มูลค่า)", 14), ("จ่าย (มูลค่า)", 14), ("ยกไป (มูลค่า)", 14),
        ]
        hr = 3
        for c, (h, w) in enumerate(heads):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, w)
        ws.freeze_panes(hr + 1, 0)
        r = hr + 1
        for l in lines:
            ws.write(r, 0, l.warehouse_id.name or "", f_text)
            ws.write(r, 1, l.location_id.complete_name if l.location_id else "", f_text)
            ws.write(r, 2, l.default_code or "", f_text)
            ws.write(r, 3, l.product_name or "", f_text)
            ws.write(r, 4, l.categ_id.complete_name or "", f_text)
            ws.write(r, 5, l.uom_id.name or "", f_text)
            ws.write_number(r, 6, l.opening_qty, f_qty)
            ws.write_number(r, 7, l.in_qty, f_qty)
            ws.write_number(r, 8, l.out_qty, f_qty)
            ws.write_number(r, 9, l.closing_qty, f_qty)
            ws.write_number(r, 10, l.unit_cost, f_val)
            ws.write_number(r, 11, l.opening_value, f_val)
            ws.write_number(r, 12, l.in_value, f_val)
            ws.write_number(r, 13, l.out_value, f_val)
            ws.write_number(r, 14, l.closing_value, f_val)
            r += 1
        if lines:
            first, last = hr + 2, r
            ws.write(r, 0, "รวม", f_tot)
            for c in range(1, 11):
                ws.write(r, c, "", f_tot)
            for c in range(11, 15):
                col = xlsxwriter.utility.xl_col_to_name(c)
                ws.write_formula(r, c, "=SUM(%s%d:%s%d)" % (col, first, col, last), f_tot_n)
        ws.autofilter(hr, 0, max(r - 1, hr), len(heads) - 1)

        # ---------- sheet 2: รายละเอียด ----------
        wd = wb.add_worksheet("รายละเอียด")
        wd.write(0, 0, "บัญชีคุมสินค้า (Stock Card) - รายละเอียดการเคลื่อนไหว", f_title)
        wd.write(1, 0, subtitle)
        dheads = [
            ("สาขา", 14), ("ตำแหน่ง", 22), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 36), ("หน่วย", 8),
            ("วันที่", 11), ("เลขที่เอกสาร", 18), ("อ้างอิง", 18), ("รายการ", 18),
            ("คู่ค้า / ตำแหน่งตรงข้าม", 28),
            ("รับ", 11), ("จ่าย", 11), ("คงเหลือ", 11), ("ต้นทุน/หน่วย", 12),
            ("มูลค่ารับ", 14), ("มูลค่าจ่าย", 14), ("มูลค่าคงเหลือ", 14),
        ]
        for c, (h, w) in enumerate(dheads):
            wd.write(hr, c, h, f_head)
            wd.set_column(c, c, w)
        wd.freeze_panes(hr + 1, 0)
        tz = pytz.timezone(self.env.user.tz or "Asia/Bangkok")
        r = hr + 1
        for l in lines:
            base = [
                l.warehouse_id.name or "",
                l.location_id.complete_name if l.location_id else "",
                l.default_code or "",
                l.product_name or "",
                l.uom_id.name or "",
            ]
            # ยอดยกมา
            for c, v in enumerate(base):
                wd.write(r, c, v, f_open)
            wd.write_datetime(r, 5, datetime.combine(self.date_from, time.min), f_date)
            wd.write(r, 6, "", f_open)
            wd.write(r, 7, "", f_open)
            wd.write(r, 8, "ยอดยกมา", f_open)
            wd.write(r, 9, "", f_open)
            wd.write(r, 10, "", f_open)
            wd.write(r, 11, "", f_open)
            wd.write_number(r, 12, l.opening_qty, f_open_n)
            wd.write(r, 13, "", f_open)
            wd.write(r, 14, "", f_open)
            wd.write(r, 15, "", f_open)
            wd.write_number(r, 16, l.opening_value, f_open_n)
            r += 1
            for m in l.move_ids:
                for c, v in enumerate(base):
                    wd.write(r, c, v, f_text)
                local_dt = pytz.utc.localize(m.date).astimezone(tz).replace(tzinfo=None)
                wd.write_datetime(r, 5, local_dt, f_date)
                wd.write(r, 6, m.reference or "", f_text)
                wd.write(r, 7, m.origin or "", f_text)
                wd.write(r, 8, m.kind or "", f_text)
                wd.write(r, 9, m.counterpart or "", f_text)
                wd.write_number(r, 10, m.in_qty, f_qty)
                wd.write_number(r, 11, m.out_qty, f_qty)
                wd.write_number(r, 12, m.balance_qty, f_qty)
                wd.write_number(r, 13, m.unit_cost, f_val)
                wd.write_number(r, 14, m.in_value, f_val)
                wd.write_number(r, 15, m.out_value, f_val)
                wd.write_number(r, 16, m.balance_value, f_val)
                r += 1
            # ยอดยกไป
            for c, v in enumerate(base):
                wd.write(r, c, v, f_tot)
            wd.write_datetime(r, 5, datetime.combine(self.date_to, time.min), f_date)
            wd.write(r, 6, "", f_tot)
            wd.write(r, 7, "", f_tot)
            wd.write(r, 8, "ยอดยกไป", f_tot)
            wd.write(r, 9, "", f_tot)
            wd.write_number(r, 10, l.in_qty, f_tot_n)
            wd.write_number(r, 11, l.out_qty, f_tot_n)
            wd.write_number(r, 12, l.closing_qty, f_tot_n)
            wd.write(r, 13, "", f_tot)
            wd.write_number(r, 14, l.in_value, f_tot_n)
            wd.write_number(r, 15, l.out_value, f_tot_n)
            wd.write_number(r, 16, l.closing_value, f_tot_n)
            r += 1
        wd.autofilter(hr, 0, max(r - 1, hr), len(dheads) - 1)

        wb.close()
        return buf.getvalue()

    # ------------------------------------------------------------------
    # helper สำหรับ QWeb
    # ------------------------------------------------------------------
    def thai_date(self, d):
        return thai_date(d)

    def local_date(self, dt):
        """datetime UTC -> วันที่ตามเขตเวลาผู้ใช้ (ใช้ใน PDF)"""
        if not dt:
            return ""
        tz = pytz.timezone(self.env.user.tz or "Asia/Bangkok")
        return thai_date(pytz.utc.localize(dt).astimezone(tz).date())


class StockCardLine(models.TransientModel):
    _name = "stock.card.line"
    _description = "บัญชีคุมสินค้า - สรุปต่อสินค้า"
    _order = "warehouse_id, location_id, default_code, product_id, id"

    wizard_id = fields.Many2one("stock.card.wizard", required=True, ondelete="cascade")
    name = fields.Char(compute="_compute_name")
    product_id = fields.Many2one("product.product", "สินค้า", required=True)
    default_code = fields.Char("รหัสสินค้า")
    product_name = fields.Char("ชื่อสินค้า")
    categ_id = fields.Many2one("product.category", "หมวด")
    uom_id = fields.Many2one("uom.uom", "หน่วย")
    warehouse_id = fields.Many2one("stock.warehouse", "สาขา / คลัง")
    location_id = fields.Many2one("stock.location", "ตำแหน่ง")
    opening_qty = fields.Float("ยกมา", digits=(16, 2))
    in_qty = fields.Float("รับ", digits=(16, 2))
    out_qty = fields.Float("จ่าย", digits=(16, 2))
    closing_qty = fields.Float("ยกไป", digits=(16, 2))
    unit_cost = fields.Float("ต้นทุน/หน่วย", digits=(16, 2))
    opening_value = fields.Float("มูลค่ายกมา", digits=(16, 2))
    in_value = fields.Float("มูลค่ารับ", digits=(16, 2))
    out_value = fields.Float("มูลค่าจ่าย", digits=(16, 2))
    closing_value = fields.Float("มูลค่ายกไป", digits=(16, 2))
    move_count = fields.Integer("จำนวนรายการ")
    move_ids = fields.One2many("stock.card.move", "line_id", "การเคลื่อนไหว")
    date_from = fields.Date(related="wizard_id.date_from")
    date_to = fields.Date(related="wizard_id.date_to")

    @api.depends("default_code", "product_name", "warehouse_id", "location_id")
    def _compute_name(self):
        for l in self:
            where = l.location_id.complete_name if l.location_id else l.warehouse_id.name
            code = "[%s] " % l.default_code if l.default_code else ""
            l.name = "%s%s - %s" % (code, l.product_name or "", where or "")


class StockCardMove(models.TransientModel):
    _name = "stock.card.move"
    _description = "บัญชีคุมสินค้า - รายการเคลื่อนไหว"
    _order = "date, id"

    line_id = fields.Many2one("stock.card.line", required=True, ondelete="cascade")
    date = fields.Datetime("วันที่")
    move_line_id = fields.Many2one("stock.move.line", "Move Line")
    picking_id = fields.Many2one("stock.picking", "ใบโอน")
    reference = fields.Char("เลขที่เอกสาร")
    origin = fields.Char("อ้างอิง")
    partner_id = fields.Many2one("res.partner", "คู่ค้า")
    location_id = fields.Many2one("stock.location", "จาก")
    location_dest_id = fields.Many2one("stock.location", "ไป")
    kind = fields.Char("รายการ")
    counterpart = fields.Char("คู่ค้า / ตำแหน่งตรงข้าม")
    in_qty = fields.Float("รับ", digits=(16, 2))
    out_qty = fields.Float("จ่าย", digits=(16, 2))
    balance_qty = fields.Float("คงเหลือ", digits=(16, 2))
    unit_cost = fields.Float("ต้นทุน/หน่วย", digits=(16, 2))
    in_value = fields.Float("มูลค่ารับ", digits=(16, 2))
    out_value = fields.Float("มูลค่าจ่าย", digits=(16, 2))
    balance_value = fields.Float("มูลค่าคงเหลือ", digits=(16, 2))

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
