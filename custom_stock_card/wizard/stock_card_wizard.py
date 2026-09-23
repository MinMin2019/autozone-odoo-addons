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
* รับ/จ่าย แตกเป็น 9 ประเภท (CATS_IN / CATS_OUT) ตาม usage ของ location ฝั่งตรงข้าม
  - ผลรวม 4 ช่องรับ = รับรวม, ผลรวม 5 ช่องจ่าย = จ่ายรวม เสมอ
  - ผ่านคลังพัก/ระหว่างทาง (transit) นับเป็น โอนเข้า/โอนออก
  - ส่งให้ลูกค้าด้วยใบขายราคา 0 บาท = "เบิกใช้" (วิธีเบิกแบบเก่าก่อนมี CONS) ไม่นับเป็นขาย
  - ตำแหน่งที่ติ๊ก is_expense_consumption (custom_branch_consumption) = "เบิกใช้"
* ตัวกรองประเภทรายการ: แสดงเฉพาะสินค้า/รายการประเภทที่เลือก แต่ยอดคงเหลือยังคิดจากทุกรายการ
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

# ประเภทรายการ (ช่องในหน้าสรุป) — ชื่อฟิลด์ = <code>_qty / <code>_value
CATS_IN = [
    ("in_purchase", "รับซื้อ"),
    ("in_return", "รับคืนจากลูกค้า"),
    ("in_transfer", "โอนเข้า"),
    ("in_other", "ปรับเพิ่ม/รับอื่น"),
]
CATS_OUT = [
    ("out_sale", "ขาย"),
    ("out_return", "ส่งคืนผู้ขาย"),
    ("out_transfer", "โอนออก"),
    ("out_consume", "เบิกใช้"),
    ("out_other", "ปรับลด/จ่ายอื่น"),
]
CATS = CATS_IN + CATS_OUT
CAT_LABEL = dict(CATS)

# ตัวกรองประเภทรายการใน wizard -> ชุดประเภทที่แสดง
KIND_FILTERS = {
    "purchase": {"in_purchase"},
    "cust_return": {"in_return"},
    "sale": {"out_sale"},
    "vendor_return": {"out_return"},
    "transfer": {"in_transfer", "out_transfer"},
    "transfer_in": {"in_transfer"},
    "transfer_out": {"out_transfer"},
    "consume": {"out_consume"},
    "other": {"in_other", "out_other"},
}


def classify(r, sign):
    """(ประเภท, ป้ายชื่อรายการ) ของบรรทัด r ในมุมของฝั่งรับ (sign>0) หรือฝั่งจ่าย (sign<0)"""
    if sign > 0:
        usage = r["src_usage"]
        label = KIND_IN.get(usage, "")
        if r["src_cons"]:
            return "in_other", "คืนเบิก"
        if usage == "supplier":
            return "in_purchase", label
        if usage == "customer":
            if r["zero_so"]:
                return "in_other", "คืนเบิก (ขายราคา 0)"
            return "in_return", label
        if usage in ("internal", "transit"):
            return "in_transfer", label
        return "in_other", label
    usage = r["dst_usage"]
    label = KIND_OUT.get(usage, "")
    if r["dst_cons"]:
        return "out_consume", "เบิกใช้"
    if usage == "supplier":
        return "out_return", label
    if usage == "customer":
        if r["zero_so"]:
            return "out_consume", "เบิกใช้ (ขายราคา 0)"
        return "out_sale", label
    if usage in ("internal", "transit"):
        return "out_transfer", label
    if usage == "production":
        return "out_consume", label
    return "out_other", label


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
    kind_filter = fields.Selection(
        [
            ("all", "ทุกประเภท"),
            ("purchase", "รับซื้อ"),
            ("cust_return", "รับคืนจากลูกค้า"),
            ("sale", "ขาย"),
            ("vendor_return", "ส่งคืนผู้ขาย"),
            ("transfer", "โอนระหว่างสาขา (เข้า + ออก)"),
            ("transfer_in", "โอนเข้า"),
            ("transfer_out", "โอนออก"),
            ("consume", "เบิกใช้"),
            ("other", "ปรับปรุงสต็อก / อื่นๆ"),
        ],
        "ประเภทรายการ", default="all", required=True,
        help="เลือกประเภท = แสดงเฉพาะสินค้าที่มีรายการประเภทนั้นในช่วงวันที่ "
        "และหน้ารายละเอียดแสดงเฉพาะรายการประเภทนั้น "
        "(ยอดยกมา/ยกไป/คงเหลือ ยังคิดจากทุกรายการตามจริง)",
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
        # ส่วนเสริมที่มีเฉพาะเมื่อโมดูลนั้นติดตั้ง (sale_stock / custom_branch_consumption)
        if "sale_line_id" in self.env["stock.move"]._fields:
            zero_so = "(sol.id IS NOT NULL AND sol.price_unit = 0)"
            sale_join = "LEFT JOIN sale_order_line sol ON sol.id = m.sale_line_id"
        else:
            zero_so, sale_join = "FALSE", ""
        if "is_expense_consumption" in self.env["stock.location"]._fields:
            src_cons = "COALESCE(ls.is_expense_consumption, FALSE)"
            dst_cons = "COALESCE(ld.is_expense_consumption, FALSE)"
        else:
            src_cons = dst_cons = "FALSE"
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
                   svl.unit_cost    AS unit_cost,
                   {zero_so}        AS zero_so,
                   {src_cons}       AS src_cons,
                   {dst_cons}       AS dst_cons
              FROM stock_move_line ml
              JOIN stock_move m       ON m.id = ml.move_id
              JOIN stock_location ls  ON ls.id = ml.location_id
              JOIN stock_location ld  ON ld.id = ml.location_dest_id
         LEFT JOIN stock_picking p    ON p.id = ml.picking_id
         {sale_join}
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
        """.format(
            zero_so=zero_so, src_cons=src_cons, dst_cons=dst_cons, sale_join=sale_join
        )
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
        show_cats = KIND_FILTERS.get(self.kind_filter)  # None = ทุกประเภท
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
            # ประเภทของแต่ละรายการในช่วง (คู่กับ in_range ตามลำดับ)
            kinds = [classify(r, 1 if q >= 0 else -1) for r, q, c in in_range]
            if show_cats is not None and not any(k[0] in show_cats for k in kinds):
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
            cat_qty = defaultdict(float)
            cat_val = defaultdict(float)
            moves = []
            for (r, q, c), (cat, kind) in zip(in_range, kinds):
                val = q * c
                bal_qty += q
                bal_val += val
                if q >= 0:
                    in_qty += q
                    in_val += val
                else:
                    out_qty += -q
                    out_val += -val
                cat_qty[cat] += abs(q)
                cat_val[cat] += abs(val)
                sign = 1 if q >= 0 else -1
                if show_cats is not None and cat not in show_cats:
                    continue
                moves.append(
                    {
                        "date": r["date"],
                        "category": cat,
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
            cat_fields = {}
            for cat, _label in CATS:
                cat_fields[cat + "_qty"] = cat_qty[cat]
                cat_fields[cat + "_value"] = cat_val[cat]
            line_vals.append(
                {
                    **cat_fields,
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
        flt = self.kind_filter_label()
        if flt:
            subtitle += "  |  เฉพาะประเภท: %s (ยอดคงเหลือคิดจากทุกรายการ)" % flt
        hr = 3

        # ---------- sheet 1: สรุป ----------
        ws = wb.add_worksheet("สรุป")
        ws.write(0, 0, "บัญชีคุมสินค้า (Stock Card) - สรุป", f_title)
        ws.write(1, 0, subtitle)
        # (หัวคอลัมน์, กว้าง, ฟิลด์/ฟังก์ชัน, ชนิด t=ข้อความ q=จำนวน v=มูลค่า(มีรวม) c=ต้นทุน)
        cols = [
            ("สาขา", 14, lambda l: l.warehouse_id.name or "", "t"),
            ("ตำแหน่ง", 22, lambda l: l.location_id.complete_name if l.location_id else "", "t"),
            ("รหัสสินค้า", 14, lambda l: l.default_code or "", "t"),
            ("ชื่อสินค้า", 40, lambda l: l.product_name or "", "t"),
            ("หมวด", 22, lambda l: l.categ_id.complete_name or "", "t"),
            ("หน่วย", 8, lambda l: l.uom_id.name or "", "t"),
            ("ยกมา (จำนวน)", 12, "opening_qty", "q"),
        ]
        cols += [(label, 12, cat + "_qty", "q") for cat, label in CATS_IN]
        cols.append(("รับรวม", 12, "in_qty", "q"))
        cols += [(label, 12, cat + "_qty", "q") for cat, label in CATS_OUT]
        cols += [
            ("จ่ายรวม", 12, "out_qty", "q"),
            ("ยกไป (จำนวน)", 12, "closing_qty", "q"),
            ("ต้นทุน/หน่วย", 12, "unit_cost", "c"),
            ("ยกมา (มูลค่า)", 14, "opening_value", "v"),
        ]
        cols += [("มูลค่า" + label, 14, cat + "_value", "v") for cat, label in CATS_IN]
        cols.append(("มูลค่ารับรวม", 14, "in_value", "v"))
        cols += [("มูลค่า" + label, 14, cat + "_value", "v") for cat, label in CATS_OUT]
        cols += [
            ("มูลค่าจ่ายรวม", 14, "out_value", "v"),
            ("ยกไป (มูลค่า)", 14, "closing_value", "v"),
        ]
        for c, (h, w, _g, _k) in enumerate(cols):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, w)
        ws.freeze_panes(hr + 1, 4)
        r = hr + 1
        for l in lines:
            for c, (_h, _w, getter, kind) in enumerate(cols):
                if kind == "t":
                    ws.write(r, c, getter(l), f_text)
                else:
                    ws.write_number(r, c, l[getter], f_qty if kind == "q" else f_val)
            r += 1
        if lines:
            first, last = hr + 2, r
            for c, (_h, _w, getter, kind) in enumerate(cols):
                if kind == "v" or getter == "closing_qty":
                    col = xlsxwriter.utility.xl_col_to_name(c)
                    ws.write_formula(
                        r, c, "=SUM(%s%d:%s%d)" % (col, first, col, last), f_tot_n
                    )
                else:
                    ws.write(r, c, "รวม" if c == 0 else "", f_tot)
        ws.autofilter(hr, 0, max(r - 1, hr), len(cols) - 1)

        # ---------- sheet 2: สรุปสาขา (มูลค่าแยกประเภท) ----------
        wb_rows, wb_total = self.branch_summary()
        wsb = wb.add_worksheet("สรุปสาขา")
        wsb.write(0, 0, "บัญชีคุมสินค้า (Stock Card) - มูลค่ารวมต่อสาขา แยกตามประเภทรายการ", f_title)
        wsb.write(1, 0, subtitle)
        bcols = [("สาขา", 18, "name"), ("ยกมา", 15, "opening")]
        bcols += [(label, 15, cat) for cat, label in CATS_IN]
        bcols.append(("รับรวม", 15, "in"))
        bcols += [(label, 15, cat) for cat, label in CATS_OUT]
        bcols += [("จ่ายรวม", 15, "out"), ("ยกไป", 15, "closing")]
        for c, (h, w, _k) in enumerate(bcols):
            wsb.write(hr, c, h, f_head)
            wsb.set_column(c, c, w)
        wsb.freeze_panes(hr + 1, 1)
        r = hr + 1
        for d in wb_rows:
            for c, (_h, _w, k) in enumerate(bcols):
                if k == "name":
                    wsb.write(r, c, d[k], f_text)
                else:
                    wsb.write_number(r, c, d[k], f_val)
            r += 1
        for c, (_h, _w, k) in enumerate(bcols):
            if k == "name":
                wsb.write(r, c, wb_total[k], f_tot)
            else:
                wsb.write_number(r, c, wb_total[k], f_tot_n)
        r += 2
        if not self.warehouse_ids and not flt:
            wsb.write(r, 0, "ตรวจสอบการโอน (ดูทุกสาขา): มูลค่าโอนออกรวม - โอนเข้ารวม =", f_open)
            wsb.write_number(
                r, 4, wb_total["out_transfer"] - wb_total["in_transfer"], f_open_n
            )
            wsb.write(
                r + 1, 0,
                "ถ้าไม่เป็น 0 = มีของออกจากสาขาต้นทางแล้วแต่ปลายทางยังไม่รับ (ค้างระหว่างทาง) "
                "หรือสาขาปลายทางอยู่นอกสิทธิ์ที่เห็น",
            )

        # ---------- sheet 3: รายละเอียด ----------
        wd = wb.add_worksheet("รายละเอียด")
        wd.write(0, 0, "บัญชีคุมสินค้า (Stock Card) - รายละเอียดการเคลื่อนไหว", f_title)
        wd.write(1, 0, subtitle)
        dheads = [
            ("สาขา", 14), ("ตำแหน่ง", 22), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 36), ("หน่วย", 8),
            ("วันที่", 11), ("เลขที่เอกสาร", 18), ("อ้างอิง", 18), ("ประเภท", 16), ("รายการ", 18),
            ("คู่ค้า / ตำแหน่งตรงข้าม", 28),
            ("รับ", 11), ("จ่าย", 11), ("คงเหลือ", 11), ("ต้นทุน/หน่วย", 12),
            ("มูลค่ารับ", 14), ("มูลค่าจ่าย", 14), ("มูลค่าคงเหลือ", 14),
        ]
        for c, (h, w) in enumerate(dheads):
            wd.write(hr, c, h, f_head)
            wd.set_column(c, c, w)
        wd.freeze_panes(hr + 1, 0)
        tz = pytz.timezone(self.env.user.tz or "Asia/Bangkok")
        ncol = len(dheads)
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
            for c in range(ncol):
                wd.write(r, c, base[c] if c < len(base) else "", f_open)
            wd.write_datetime(r, 5, datetime.combine(self.date_from, time.min), f_date)
            wd.write(r, 9, "ยอดยกมา", f_open)
            wd.write_number(r, 13, l.opening_qty, f_open_n)
            wd.write_number(r, 17, l.opening_value, f_open_n)
            r += 1
            for m in l.move_ids:
                for c, v in enumerate(base):
                    wd.write(r, c, v, f_text)
                local_dt = pytz.utc.localize(m.date).astimezone(tz).replace(tzinfo=None)
                wd.write_datetime(r, 5, local_dt, f_date)
                wd.write(r, 6, m.reference or "", f_text)
                wd.write(r, 7, m.origin or "", f_text)
                wd.write(r, 8, CAT_LABEL.get(m.category, ""), f_text)
                wd.write(r, 9, m.kind or "", f_text)
                wd.write(r, 10, m.counterpart or "", f_text)
                wd.write_number(r, 11, m.in_qty, f_qty)
                wd.write_number(r, 12, m.out_qty, f_qty)
                wd.write_number(r, 13, m.balance_qty, f_qty)
                wd.write_number(r, 14, m.unit_cost, f_val)
                wd.write_number(r, 15, m.in_value, f_val)
                wd.write_number(r, 16, m.out_value, f_val)
                wd.write_number(r, 17, m.balance_value, f_val)
                r += 1
            # ยอดยกไป (รับ/จ่ายรวมของทุกประเภท แม้กรองประเภทอยู่)
            for c in range(ncol):
                wd.write(r, c, base[c] if c < len(base) else "", f_tot)
            wd.write_datetime(r, 5, datetime.combine(self.date_to, time.min), f_date)
            wd.write(r, 9, "ยอดยกไป (รวมทุกประเภท)" if flt else "ยอดยกไป", f_tot)
            wd.write_number(r, 11, l.in_qty, f_tot_n)
            wd.write_number(r, 12, l.out_qty, f_tot_n)
            wd.write_number(r, 13, l.closing_qty, f_tot_n)
            wd.write_number(r, 15, l.in_value, f_tot_n)
            wd.write_number(r, 16, l.out_value, f_tot_n)
            wd.write_number(r, 17, l.closing_value, f_tot_n)
            r += 1
        wd.autofilter(hr, 0, max(r - 1, hr), len(dheads) - 1)

        wb.close()
        return buf.getvalue()

    # ------------------------------------------------------------------
    # helper สำหรับ QWeb / Excel
    # ------------------------------------------------------------------
    def cat_labels(self):
        """[(code, ป้ายชื่อ)] ของ 9 ประเภท เรียงตามคอลัมน์"""
        return list(CATS)

    def kind_filter_label(self):
        self.ensure_one()
        if self.kind_filter == "all":
            return ""
        return dict(self._fields["kind_filter"].selection).get(self.kind_filter, "")

    def branch_summary(self):
        """มูลค่ารวมต่อสาขา แยกตามประเภท (แถวรวมท้ายสาขา) + แถวรวมทั้งหมด

        คืน (rows, total) — แต่ละตัวเป็น dict: name, opening, <cat>..., in, out, closing
        """
        self.ensure_one()
        keys = ["opening", "in", "out", "closing"] + [c for c, _l in CATS]
        by_wh = {}
        for l in self.line_ids:
            d = by_wh.get(l.warehouse_id.id)
            if d is None:
                d = dict.fromkeys(keys, 0.0)
                d["name"] = l.warehouse_id.name or ""
                by_wh[l.warehouse_id.id] = d
            d["opening"] += l.opening_value
            d["in"] += l.in_value
            d["out"] += l.out_value
            d["closing"] += l.closing_value
            for c, _l in CATS:
                d[c] += l[c + "_value"]
        rows = sorted(by_wh.values(), key=lambda d: d["name"])
        total = dict.fromkeys(keys, 0.0)
        total["name"] = "รวมทุกสาขา"
        for d in rows:
            for k in keys:
                total[k] += d[k]
        return rows, total

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
    # รับ/จ่าย แตกตามประเภท (ผลรวม in_* = in_qty, ผลรวม out_* = out_qty)
    in_purchase_qty = fields.Float("รับซื้อ", digits=(16, 2))
    in_return_qty = fields.Float("รับคืนลูกค้า", digits=(16, 2))
    in_transfer_qty = fields.Float("โอนเข้า", digits=(16, 2))
    in_other_qty = fields.Float("ปรับเพิ่ม/รับอื่น", digits=(16, 2))
    out_sale_qty = fields.Float("ขาย", digits=(16, 2))
    out_return_qty = fields.Float("ส่งคืนผู้ขาย", digits=(16, 2))
    out_transfer_qty = fields.Float("โอนออก", digits=(16, 2))
    out_consume_qty = fields.Float("เบิกใช้", digits=(16, 2))
    out_other_qty = fields.Float("ปรับลด/จ่ายอื่น", digits=(16, 2))
    in_purchase_value = fields.Float("มูลค่ารับซื้อ", digits=(16, 2))
    in_return_value = fields.Float("มูลค่ารับคืนลูกค้า", digits=(16, 2))
    in_transfer_value = fields.Float("มูลค่าโอนเข้า", digits=(16, 2))
    in_other_value = fields.Float("มูลค่าปรับเพิ่ม/รับอื่น", digits=(16, 2))
    out_sale_value = fields.Float("มูลค่าขาย (ทุน)", digits=(16, 2))
    out_return_value = fields.Float("มูลค่าส่งคืนผู้ขาย", digits=(16, 2))
    out_transfer_value = fields.Float("มูลค่าโอนออก", digits=(16, 2))
    out_consume_value = fields.Float("มูลค่าเบิกใช้", digits=(16, 2))
    out_other_value = fields.Float("มูลค่าปรับลด/จ่ายอื่น", digits=(16, 2))
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
    category = fields.Selection(CATS, "ประเภท")
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
