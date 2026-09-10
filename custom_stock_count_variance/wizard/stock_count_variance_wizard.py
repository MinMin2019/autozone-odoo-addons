# -*- coding: utf-8 -*-
"""ผลต่างตรวจนับสต็อก (Physical Count Variance)

โหมด pending  : stock.quant ที่ inventory_quantity_set = True (นับแล้ว ยังไม่ Apply)
                ระบบ = quant.quantity, นับได้ = inventory_quantity, ผลต่าง = inventory_diff_quantity
                ต้นทุน = standard_price ปัจจุบัน, ผู้นับ = quant.user_id
                + ตัวเลือก: รายการที่ถึงกำหนดนับ (inventory_date <= วันที่) แต่ยังไม่นับ
โมด applied   : stock.move ที่ is_inventory = True และ done ในช่วงวันที่ (ไม่รวม Scrap)
                ผลต่าง = +qty ถ้าเข้าคลัง / -qty ถ้าออกจากคลัง
                ระบบก่อนปรับ = ยอดสะสมของ (สินค้า, ตำแหน่ง) ก่อน move นั้น, นับได้ = ระบบก่อนปรับ + ผลต่าง
                ต้นทุน = SVL ของ move ถ้าไม่มีใช้ standard_price, ผู้ปรับ = create_uid ของ move
"""
import base64
import io
import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


def thai_date(d):
    if not d:
        return ""
    return "%02d/%02d/%d" % (d.day, d.month, d.year + 543)


class StockCountVarianceWizard(models.TransientModel):
    _name = "stock.count.variance.wizard"
    _description = "ผลต่างตรวจนับสต็อก"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    mode = fields.Selection(
        [("pending", "รอปรับปรุง (นับแล้ว ยังไม่ Apply)"),
         ("applied", "ปรับปรุงแล้ว (ประวัติตามช่วงวันที่)")],
        string="โหมด", required=True, default="pending",
    )
    date_from = fields.Date(
        "ตั้งแต่วันที่",
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date("ถึงวันที่", required=True, default=fields.Date.context_today)
    warehouse_ids = fields.Many2many(
        "stock.warehouse", string="สาขา / คลัง", help="เว้นว่าง = ทุกสาขาที่มีสิทธิ์เห็น"
    )
    product_ids = fields.Many2many("product.product", string="สินค้า")
    categ_ids = fields.Many2many("product.category", string="หมวดสินค้า")
    include_uncounted = fields.Boolean(
        "รวมรายการที่ถึงกำหนดนับแต่ยังไม่นับ",
        help="โหมดรอปรับปรุง: แสดง quant ที่ Scheduled Date ถึงแล้วแต่ยังไม่กรอกยอดนับ",
    )
    only_diff = fields.Boolean(
        "เฉพาะรายการที่มีผลต่าง", default=False,
        help="ปิด = แสดงรายการที่นับตรงด้วย (ใช้คำนวณความแม่นยำ)",
    )
    line_ids = fields.One2many("stock.count.variance.line", "wizard_id")
    line_count = fields.Integer(compute="_compute_line_count")

    @api.depends("mode", "date_from", "date_to")
    def _compute_name(self):
        for w in self:
            if w.mode == "applied":
                w.name = "ผลต่างตรวจนับ (ปรับปรุงแล้ว) %s - %s" % (
                    thai_date(w.date_from), thai_date(w.date_to))
            else:
                w.name = "ผลต่างตรวจนับ (รอปรับปรุง) ณ %s" % thai_date(w.date_to)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for w in self:
            w.line_count = len(w.line_ids)

    @api.constrains("date_from", "date_to", "mode")
    def _check_dates(self):
        for w in self:
            if w.mode == "applied" and w.date_from and w.date_to and w.date_from > w.date_to:
                raise UserError(_("วันที่เริ่มต้องไม่เกินวันที่สิ้นสุด"))

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

    def _product_domain(self):
        domain = []
        if self.product_ids:
            domain.append(("product_id", "in", self.product_ids.ids))
        if self.categ_ids:
            domain.append(("product_id.categ_id", "child_of", self.categ_ids.ids))
        return domain

    def _tz(self):
        return pytz.timezone(self.env.user.tz or "Asia/Bangkok")

    def _to_utc(self, d):
        local = self._tz().localize(datetime.combine(d, time.min))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _local_date(self, dt):
        if not dt:
            return False
        return pytz.utc.localize(dt).astimezone(self._tz()).date()

    # ------------------------------------------------------------------
    # คำนวณ
    # ------------------------------------------------------------------
    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        if self.mode == "pending":
            vals = self._compute_pending()
        else:
            vals = self._compute_applied()
        lines = self.env["stock.count.variance.line"].create(vals)
        _logger.info("stock count variance (%s): %d lines", self.mode, len(lines))
        return lines

    def _line_base(self, product, location, wh):
        return {
            "wizard_id": self.id,
            "product_id": product.id,
            "default_code": product.default_code or "",
            "product_name": product.name,
            "categ_id": product.categ_id.id,
            "uom_id": product.uom_id.id,
            "warehouse_id": wh.id if wh else False,
            "location_id": location.id,
        }

    def _compute_pending(self):
        warehouses = self._get_scope_warehouses()
        Quant = self.env["stock.quant"].sudo()
        base_domain = [
            ("company_id", "=", self.company_id.id),
            ("location_id.usage", "=", "internal"),
            ("location_id.warehouse_id", "in", warehouses.ids),
        ] + self._product_domain()
        counted = Quant.search(base_domain + [("inventory_quantity_set", "=", True)])
        uncounted = Quant.browse()
        if self.include_uncounted:
            uncounted = Quant.search(
                base_domain
                + [("inventory_quantity_set", "=", False),
                   ("inventory_date", "!=", False),
                   ("inventory_date", "<=", self.date_to)]
            )
        vals = []
        for q in counted:
            product = q.product_id.with_company(self.company_id)
            rounding = product.uom_id.rounding or 0.001
            # ไม่ใช้ inventory_diff_quantity ที่เก็บไว้ เพราะ Odoo คำนวณตอนกรอกยอดนับเท่านั้น
            # ถ้ายอดระบบขยับหลังนับ (is_outdated) ค่าที่เก็บจะค้าง
            diff = (q.inventory_quantity or 0.0) - (q.quantity or 0.0)
            if self.only_diff and float_is_zero(diff, precision_rounding=rounding):
                continue
            cost = product.standard_price or 0.0
            v = self._line_base(product, q.location_id, q.location_id.warehouse_id)
            v.update(
                {
                    "state": "counted",
                    "date": q.write_date,
                    "inventory_date": q.inventory_date,
                    "system_qty": q.quantity,
                    "counted_qty": q.inventory_quantity,
                    "diff_qty": diff,
                    "unit_cost": cost,
                    "diff_value": diff * cost,
                    "abs_diff_value": abs(diff * cost),
                    "user_id": q.user_id.id or q.write_uid.id,
                    "reference": "",
                    "quant_id": q.id,
                    "lot_id": q.lot_id.id,
                    "is_outdated": q.is_outdated,
                }
            )
            vals.append(v)
        for q in uncounted:
            product = q.product_id.with_company(self.company_id)
            v = self._line_base(product, q.location_id, q.location_id.warehouse_id)
            v.update(
                {
                    "state": "uncounted",
                    "date": False,
                    "inventory_date": q.inventory_date,
                    "system_qty": q.quantity,
                    "counted_qty": 0.0,
                    "diff_qty": 0.0,
                    "unit_cost": product.standard_price or 0.0,
                    "diff_value": 0.0,
                    "abs_diff_value": 0.0,
                    "user_id": q.user_id.id,
                    "reference": "",
                    "quant_id": q.id,
                    "lot_id": q.lot_id.id,
                }
            )
            vals.append(v)
        return vals

    def _compute_applied(self):
        if not self.date_from:
            raise UserError(_("โหมดปรับปรุงแล้วต้องระบุวันที่เริ่ม"))
        warehouses = self._get_scope_warehouses()
        start, end = self._to_utc(self.date_from), self._to_utc(self.date_to + timedelta(days=1))
        product_ids = None
        if self.product_ids or self.categ_ids:
            product_ids = self.env["product.product"].with_context(active_test=False).search(
                [(k.replace("product_id.", "").replace("product_id", "id"), op, v)
                 for k, op, v in self._product_domain()]
            ).ids
        query = """
            SELECT ml.id AS ml_id, ml.date, ml.product_id, ml.quantity_product_uom AS qty,
                   ml.reference, ml.lot_id, m.id AS move_id, m.origin, m.create_uid,
                   CASE WHEN ld.usage = 'internal' THEN ld.id ELSE ls.id END AS loc_id,
                   CASE WHEN ld.usage = 'internal' THEN 1 ELSE -1 END AS sign,
                   CASE WHEN ld.usage = 'internal' THEN ld.warehouse_id ELSE ls.warehouse_id END AS wh_id,
                   svl.unit_cost,
                   (SELECT COALESCE(SUM(CASE WHEN x.location_dest_id = loc.id THEN x.quantity_product_uom ELSE 0 END)
                                  - SUM(CASE WHEN x.location_id = loc.id THEN x.quantity_product_uom ELSE 0 END), 0)
                      FROM stock_move_line x
                     WHERE x.state = 'done' AND x.product_id = ml.product_id
                       AND (x.location_id = loc.id OR x.location_dest_id = loc.id)
                       AND (x.date < ml.date OR (x.date = ml.date AND x.id < ml.id))
                   ) AS system_before
              FROM stock_move_line ml
              JOIN stock_move m      ON m.id = ml.move_id
              JOIN stock_location ls ON ls.id = ml.location_id
              JOIN stock_location ld ON ld.id = ml.location_dest_id
              JOIN stock_location loc ON loc.id = CASE WHEN ld.usage = 'internal' THEN ld.id ELSE ls.id END
         LEFT JOIN (
                   SELECT stock_move_id,
                          CASE WHEN SUM(quantity) <> 0 THEN SUM(value) / SUM(quantity) END AS unit_cost
                     FROM stock_valuation_layer WHERE stock_move_id IS NOT NULL GROUP BY stock_move_id
                   ) svl ON svl.stock_move_id = m.id
             WHERE m.is_inventory = TRUE
               AND ml.state = 'done'
               AND m.company_id = %(company)s
               AND ml.date >= %(start)s AND ml.date < %(end)s
               AND ((ld.usage = 'internal' AND ls.usage = 'inventory' AND NOT ls.scrap_location)
                 OR (ls.usage = 'internal' AND ld.usage = 'inventory' AND NOT ld.scrap_location))
               AND loc.warehouse_id = ANY(%(wh)s)
        """
        params = {"company": self.company_id.id, "start": start, "end": end, "wh": warehouses.ids}
        if product_ids is not None:
            query += " AND ml.product_id = ANY(%(products)s)"
            params["products"] = product_ids
        query += " ORDER BY ml.date, ml.id"
        self.env.flush_all()
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()

        Product = self.env["product.product"].with_context(active_test=False).with_company(self.company_id)
        prod_by_id = {p.id: p for p in Product.browse({r["product_id"] for r in rows})}
        loc_by_id = {l.id: l for l in self.env["stock.location"].browse({r["loc_id"] for r in rows})}
        wh_by_id = {w.id: w for w in self.env["stock.warehouse"].browse({r["wh_id"] for r in rows if r["wh_id"]})}

        vals = []
        for r in rows:
            product = prod_by_id[r["product_id"]]
            rounding = product.uom_id.rounding or 0.001
            diff = r["sign"] * (r["qty"] or 0.0)
            if self.only_diff and float_is_zero(diff, precision_rounding=rounding):
                continue
            cost = r["unit_cost"]
            if cost is None:
                cost = product.standard_price or 0.0
            cost = abs(cost)
            before = r["system_before"] or 0.0
            v = self._line_base(product, loc_by_id[r["loc_id"]], wh_by_id.get(r["wh_id"]))
            v.update(
                {
                    "state": "applied",
                    "date": r["date"],
                    "inventory_date": self._local_date(r["date"]),
                    "system_qty": before,
                    "counted_qty": before + diff,
                    "diff_qty": diff,
                    "unit_cost": cost,
                    "diff_value": diff * cost,
                    "abs_diff_value": abs(diff * cost),
                    "user_id": r["create_uid"],
                    "reference": r["reference"] or r["origin"] or "",
                    "move_id": r["move_id"],
                    "lot_id": r["lot_id"],
                }
            )
            vals.append(v)
        return vals

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
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "stock.count.variance.line",
            "view_mode": "list,form,pivot,graph",
            "domain": [("wizard_id", "=", self.id)],
            "context": {
                "group_by": ["warehouse_id"],
                "mode": self.mode,
                "create": False, "edit": False, "delete": False,
            },
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._ensure_lines()
        return self.env.ref(
            "custom_stock_count_variance.action_report_stock_count_variance"
        ).report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self._ensure_lines()
        data = self._build_xlsx(lines)
        fname = "CountVariance_%s_%s.xlsx" % (self.mode, self.date_to.strftime("%Y%m%d"))
        attachment = self.env["ir.attachment"].create(
            {
                "name": fname, "type": "binary", "datas": base64.b64encode(data),
                "res_model": self._name, "res_id": self.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        return {"type": "ir.actions.act_url",
                "url": "/web/content/%d?download=true" % attachment.id, "target": "self"}

    # ------------------------------------------------------------------
    # สรุป (ใช้ทั้ง PDF และ Excel)
    # ------------------------------------------------------------------
    def warehouse_summary(self):
        """[(warehouse, lines, stats)] stats = dict(lines, counted, matched, short_qty, short_value,
        over_qty, over_value, net_value, accuracy)"""
        self.ensure_one()
        groups = []
        for l in self.line_ids:
            if groups and groups[-1][0] == l.warehouse_id:
                groups[-1][1].append(l)
            else:
                groups.append((l.warehouse_id, [l]))
        out = []
        for wh, lines in groups:
            out.append((wh, lines, self._stats(lines)))
        return out

    def _stats(self, lines):
        counted = [l for l in lines if l.state != "uncounted"]
        matched = [l for l in counted if float_is_zero(l.diff_qty, precision_digits=3)]
        short = [l for l in counted if l.diff_qty < 0]
        over = [l for l in counted if l.diff_qty > 0]
        return {
            "lines": len(lines),
            "counted": len(counted),
            "uncounted": len(lines) - len(counted),
            "matched": len(matched),
            "short_lines": len(short),
            "short_value": sum(l.diff_value for l in short),
            "over_lines": len(over),
            "over_value": sum(l.diff_value for l in over),
            "net_value": sum(l.diff_value for l in counted),
            "abs_value": sum(l.abs_diff_value for l in counted),
            "accuracy": (len(matched) * 100.0 / len(counted)) if counted else 0.0,
        }

    def total_stats(self):
        self.ensure_one()
        return self._stats(list(self.line_ids))

    def thai_date(self, d):
        return thai_date(d)

    def local_date(self, dt):
        return thai_date(self._local_date(dt)) if dt else ""

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------
    def _build_xlsx(self, lines):
        import xlsxwriter

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        f_title = wb.add_format({"bold": True, "font_size": 14})
        f_head = wb.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1,
                                "align": "center", "valign": "vcenter", "text_wrap": True})
        f_text = wb.add_format({"border": 1})
        f_num = wb.add_format({"border": 1, "num_format": "#,##0.00;[Red]-#,##0.00"})
        f_pct = wb.add_format({"border": 1, "num_format": "0.00"})
        f_date = wb.add_format({"border": 1, "num_format": "dd/mm/yyyy"})
        f_tot = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA"})
        f_tot_n = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA",
                                 "num_format": "#,##0.00;[Red]-#,##0.00"})
        f_tot_p = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA", "num_format": "0.00"})
        mode_label = "รอปรับปรุง" if self.mode == "pending" else "ปรับปรุงแล้ว"
        who_label = "ผู้นับ" if self.mode == "pending" else "ผู้ปรับปรุง"
        subtitle = "%s | %s" % (
            mode_label,
            ("ณ %s" % self.date_to.strftime("%d/%m/%Y")) if self.mode == "pending"
            else "%s ถึง %s" % (self.date_from.strftime("%d/%m/%Y"), self.date_to.strftime("%d/%m/%Y")),
        )

        # ---------- sheet 1: สรุปต่อสาขา ----------
        ws = wb.add_worksheet("สรุปสาขา")
        ws.write(0, 0, "ผลต่างตรวจนับสต็อก - สรุปต่อสาขา", f_title)
        ws.write(1, 0, subtitle)
        heads = [("สาขา", 14), ("รายการ", 9), ("นับแล้ว", 9), ("ยังไม่นับ", 9), ("ตรง", 8),
                 ("ขาด (รายการ)", 10), ("มูลค่าขาด", 14), ("เกิน (รายการ)", 10), ("มูลค่าเกิน", 14),
                 ("สุทธิ", 14), ("ผลต่างรวม (abs)", 14), ("ความแม่นยำ %", 11)]
        hr = 3
        for c, (h, w) in enumerate(heads):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, w)
        r = hr + 1
        for wh, _lines, s in self.warehouse_summary():
            ws.write(r, 0, wh.name if wh else "-", f_text)
            for c, k in enumerate(["lines", "counted", "uncounted", "matched", "short_lines"], 1):
                ws.write_number(r, c, s[k], f_text)
            ws.write_number(r, 6, s["short_value"], f_num)
            ws.write_number(r, 7, s["over_lines"], f_text)
            ws.write_number(r, 8, s["over_value"], f_num)
            ws.write_number(r, 9, s["net_value"], f_num)
            ws.write_number(r, 10, s["abs_value"], f_num)
            ws.write_number(r, 11, s["accuracy"], f_pct)
            r += 1
        t = self.total_stats()
        ws.write(r, 0, "รวม", f_tot)
        for c, k in enumerate(["lines", "counted", "uncounted", "matched", "short_lines"], 1):
            ws.write_number(r, c, t[k], f_tot)
        ws.write_number(r, 6, t["short_value"], f_tot_n)
        ws.write_number(r, 7, t["over_lines"], f_tot)
        ws.write_number(r, 8, t["over_value"], f_tot_n)
        ws.write_number(r, 9, t["net_value"], f_tot_n)
        ws.write_number(r, 10, t["abs_value"], f_tot_n)
        ws.write_number(r, 11, t["accuracy"], f_tot_p)

        # ---------- sheet 2: รายการ ----------
        wd = wb.add_worksheet("รายการ")
        wd.write(0, 0, "ผลต่างตรวจนับสต็อก - รายการ", f_title)
        wd.write(1, 0, subtitle)
        dheads = [("สาขา", 12), ("ตำแหน่ง", 18), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 38), ("หมวด", 20),
                  ("หน่วย", 8), ("Lot", 12), ("สถานะ", 10), ("วันที่", 11), ("กำหนดนับ", 11),
                  ("ยอดระบบ", 11), ("ยอดนับ", 11), ("ผลต่าง", 11), ("ต้นทุน/หน่วย", 11),
                  ("มูลค่าผลต่าง", 13), (who_label, 18), ("อ้างอิง / เหตุผล", 24)]
        for c, (h, w) in enumerate(dheads):
            wd.write(hr, c, h, f_head)
            wd.set_column(c, c, w)
        wd.freeze_panes(hr + 1, 4)
        r = hr + 1
        state_label = dict(self.env["stock.count.variance.line"]._fields["state"].selection)
        for l in lines:
            wd.write(r, 0, l.warehouse_id.name or "", f_text)
            wd.write(r, 1, l.location_id.complete_name or "", f_text)
            wd.write(r, 2, l.default_code or "", f_text)
            wd.write(r, 3, l.product_name or "", f_text)
            wd.write(r, 4, l.categ_id.complete_name or "", f_text)
            wd.write(r, 5, l.uom_id.name or "", f_text)
            wd.write(r, 6, l.lot_id.name or "", f_text)
            wd.write(r, 7, state_label.get(l.state, ""), f_text)
            d = self._local_date(l.date)
            if d:
                wd.write_datetime(r, 8, datetime.combine(d, time.min), f_date)
            else:
                wd.write(r, 8, "", f_text)
            if l.inventory_date:
                wd.write_datetime(r, 9, datetime.combine(l.inventory_date, time.min), f_date)
            else:
                wd.write(r, 9, "", f_text)
            wd.write_number(r, 10, l.system_qty, f_num)
            wd.write_number(r, 11, l.counted_qty, f_num)
            wd.write_number(r, 12, l.diff_qty, f_num)
            wd.write_number(r, 13, l.unit_cost, f_num)
            wd.write_number(r, 14, l.diff_value, f_num)
            wd.write(r, 15, l.user_id.name or "", f_text)
            wd.write(r, 16, l.reference or "", f_text)
            r += 1
        if lines:
            wd.write(r, 0, "รวม", f_tot)
            for c in range(1, len(dheads)):
                wd.write(r, c, "", f_tot)
            col = xlsxwriter.utility.xl_col_to_name(14)
            wd.write_formula(r, 14, "=SUM(%s%d:%s%d)" % (col, hr + 2, col, r), f_tot_n)
        wd.autofilter(hr, 0, max(r - 1, hr), len(dheads) - 1)
        wb.close()
        return buf.getvalue()


class StockCountVarianceLine(models.TransientModel):
    _name = "stock.count.variance.line"
    _description = "ผลต่างตรวจนับสต็อก - รายการ"
    _order = "warehouse_id, location_id, default_code, product_id, date, id"

    wizard_id = fields.Many2one("stock.count.variance.wizard", required=True, ondelete="cascade")
    name = fields.Char(compute="_compute_name")
    state = fields.Selection(
        [("counted", "นับแล้ว รอ Apply"), ("uncounted", "ถึงกำหนด ยังไม่นับ"), ("applied", "ปรับปรุงแล้ว")],
        string="สถานะ",
    )
    product_id = fields.Many2one("product.product", "สินค้า", required=True)
    default_code = fields.Char("รหัสสินค้า")
    product_name = fields.Char("ชื่อสินค้า")
    categ_id = fields.Many2one("product.category", "หมวด")
    uom_id = fields.Many2one("uom.uom", "หน่วย")
    lot_id = fields.Many2one("stock.lot", "Lot")
    warehouse_id = fields.Many2one("stock.warehouse", "สาขา / คลัง")
    location_id = fields.Many2one("stock.location", "ตำแหน่ง")
    date = fields.Datetime("วันที่")
    inventory_date = fields.Date("กำหนดนับ")
    system_qty = fields.Float("ยอดระบบ", digits=(16, 2))
    counted_qty = fields.Float("ยอดนับ", digits=(16, 2))
    diff_qty = fields.Float("ผลต่าง", digits=(16, 2))
    unit_cost = fields.Float("ต้นทุน/หน่วย", digits=(16, 2))
    diff_value = fields.Float("มูลค่าผลต่าง", digits=(16, 2))
    abs_diff_value = fields.Float("ผลต่าง (abs)", digits=(16, 2))
    diff_pct = fields.Float("ผลต่าง %", digits=(16, 2), compute="_compute_pct")
    user_id = fields.Many2one("res.users", "ผู้นับ / ผู้ปรับ")
    reference = fields.Char("อ้างอิง / เหตุผล")
    quant_id = fields.Many2one("stock.quant", "Quant")
    is_outdated = fields.Boolean("ยอดระบบขยับหลังนับ", help="มีการเคลื่อนไหวหลังกรอกยอดนับ ควรนับใหม่ก่อน Apply")
    move_id = fields.Many2one("stock.move", "Move")

    @api.depends("default_code", "product_name", "location_id")
    def _compute_name(self):
        for l in self:
            code = "[%s] " % l.default_code if l.default_code else ""
            l.name = "%s%s - %s" % (code, l.product_name or "", l.location_id.complete_name or "")

    @api.depends("system_qty", "diff_qty")
    def _compute_pct(self):
        for l in self:
            l.diff_pct = (l.diff_qty * 100.0 / l.system_qty) if l.system_qty else 0.0

    def action_open_source(self):
        self.ensure_one()
        if self.move_id:
            return {"type": "ir.actions.act_window", "res_model": "stock.move",
                    "res_id": self.move_id.id, "view_mode": "form", "target": "current"}
        if self.quant_id:
            return {"type": "ir.actions.act_window", "res_model": "stock.quant",
                    "res_id": self.quant_id.id, "view_mode": "form", "target": "current",
                    "context": {"inventory_mode": True}}
        return False
