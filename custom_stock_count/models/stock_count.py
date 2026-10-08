# -*- coding: utf-8 -*-
"""ใบตรวจนับสต็อก (Physical Count Sheet) + กระทบยอด — จบในจอเดียว

แนวคิด (ตามแบบฟอร์ม Autozone-แบบฟอร์มตรวจนับสต๊อก v3):
  * ยอดตามบัญชีตัด ณ "วันตัดยอด" (date_cutoff) แต่ไปนับของจริง "วันนับ" (date_count) ซึ่งอาจเป็นคนละวัน
    ระหว่างสองวันนี้มีรับเข้า/จ่ายออก ต้องเดินยอดไปข้างหน้าก่อนแล้วค่อยเทียบ:
        ยอดที่ควรมี ณ วันนับ = ยอดตามบัญชี ณ วันตัดยอด + รับเข้า - จ่ายออก (ช่วงหลังวันตัดยอดถึงสิ้นวันนับ)
        ผลต่าง = ตรวจนับได้ - ยอดที่ควรมี   (ติดลบ = ขาด, บวก = เกิน)
    Odoo ดึง "รับเข้า/จ่ายออก" จาก stock.move.line (done) ให้เองตามคลัง ไม่ต้องกรอกมือ
  * ตรวจนับเพื่อตรวจสอบและหาสาเหตุ ไม่ใช่เพื่อปรับยอดให้ตรง → ทุกผลต่างต้องมีสาเหตุ/เอกสาร/ผู้รับผิดชอบ
    ปิดใบได้ 2 ทาง: "ปิดใบ ไม่ปรับระบบ" (closed, แก้ที่ต้นทาง) หรือ "ปรับปรุงสต็อก" (done, Inventory Manager)

สถานะ: ร่าง → กำลังนับ → นับแล้ว รอสรุป → (กระทบยอดแล้ว ไม่ปรับระบบ | ปรับปรุงแล้ว) / ยกเลิก

* ยอดตามบัญชี ณ วันตัดยอด = ยอด quant ปัจจุบัน - สุทธิของ move หลังสิ้นวันตัดยอด (ย้อนยอดกลับ)
  จึงคำนวณใหม่ได้ทุกเมื่อ (ปุ่ม "รีเฟรชยอดระบบ") ไม่ขึ้นกับว่าดึงรายการวันไหน
* ปรับปรุงสต็อก = ปรับ "เท่าผลต่าง" ลงบน quant ปัจจุบัน (ไม่ใช่ตั้งยอดเท่าที่นับ) เพราะหลังวันนับอาจมีรับ/จ่ายต่อ
* สินค้า 1 ตัวที่มีของอยู่หลาย location ลูก → ปรับปรุงไม่ได้ ต้องแยกใบนับตาม location
"""
from collections import defaultdict
from datetime import datetime, time

import pytz
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, float_round

COUNT_TYPES = [("monthly", "ประจำเดือน"), ("yearly", "ประจำปี"), ("spot", "สุ่มตรวจ")]
STATES = [
    ("draft", "ร่าง"),
    ("counting", "กำลังนับ"),
    ("counted", "นับแล้ว รอสรุป"),
    ("closed", "กระทบยอดแล้ว ไม่ปรับระบบ"),
    ("done", "ปรับปรุงสต็อกแล้ว"),
    ("cancel", "ยกเลิก"),
]
LINE_STATUS = [
    ("none", "ยังไม่ได้นับ"),
    ("match", "ตรง"),
    ("short", "ขาด"),
    ("over", "เกิน"),
]


class StockCount(models.Model):
    _name = "az.stock.count"
    _description = "ใบตรวจนับสต็อก"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char("เลขที่ใบนับ", default="/", readonly=True, copy=False)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, readonly=True
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse", "สาขา / คลังที่นับ", required=True, tracking=True,
        default=lambda self: self._default_warehouse(),
    )
    location_id = fields.Many2one(
        "stock.location", "ตำแหน่งเก็บ", required=True, tracking=True,
        compute="_compute_location_id", store=True, readonly=False, precompute=True,
        domain="[('usage', '=', 'internal'), ('warehouse_id', '=', warehouse_id)]",
    )
    date_cutoff = fields.Date(
        "ยอดตามบัญชี ณ วันที่", required=True, default=fields.Date.context_today, tracking=True,
        help="วันตัดยอดบัญชี (สิ้นวัน) ที่ใช้เป็นฐาน — ปกติ = วันสิ้นเดือน; ถ้านับวันเดียวกับตัดยอดให้ใส่วันเดียวกัน",
    )
    date_count = fields.Date(
        "ตรวจนับจริงวันที่", required=True, default=fields.Date.context_today, tracking=True,
    )
    snapshot_date = fields.Datetime("คำนวณยอดล่าสุดเมื่อ", readonly=True, copy=False)
    count_type = fields.Selection(COUNT_TYPES, "รอบการนับ", required=True, default="monthly", tracking=True)
    counter1 = fields.Char("ผู้นับคนที่ 1")
    counter2 = fields.Char("ผู้นับคนที่ 2")
    checker = fields.Char("ผู้ทาน / หัวหน้าคลัง")
    summarizer = fields.Char("ผู้สรุปผลต่าง")
    accountant = fields.Char("ฝ่ายบัญชี")
    approver = fields.Char("ผู้อนุมัติ")
    blind = fields.Boolean(
        "ใบตรวจนับไม่แสดงยอดตามบัญชี (นับแบบไม่เห็นยอด)", default=False,
        help="ติ๊ก = PDF/Excel ใบตรวจนับเว้นช่องยอดตามบัญชี/มูลค่า/ผลต่างไว้ ให้ผู้นับนับของจริงก่อน "
             "ยอดตามบัญชีจะแสดงเฉพาะชีต/รายงานกระทบยอด",
    )
    include_zero = fields.Boolean(
        "รวมสินค้าที่ยอดเป็น 0 แต่เคยมีในคลัง", default=False,
        help="ติ๊ก = เอาสินค้าที่เคยรับเข้าคลังนี้แต่ยอด 0 ใส่ในใบนับด้วย (เผื่อนับเจอของที่ระบบว่าหมด)",
    )
    categ_ids = fields.Many2many(
        "product.category", string="เฉพาะหมวดสินค้า",
        help="ว่าง = ทุกหมวด; เลือกแล้วจะดึงเฉพาะสินค้าในหมวดนั้น (รวมหมวดย่อย)",
    )
    state = fields.Selection(STATES, "สถานะ", default="draft", required=True, tracking=True, copy=False)
    line_ids = fields.One2many("az.stock.count.line", "count_id", "รายการนับ", copy=True)
    note = fields.Text("หมายเหตุ")
    user_id = fields.Many2one("res.users", "ผู้สร้าง", default=lambda self: self.env.user, readonly=True)
    closed_by = fields.Many2one("res.users", "ผู้ปิดใบ / ผู้ปรับปรุง", readonly=True, copy=False)
    closed_date = fields.Datetime("ปิดใบเมื่อ", readonly=True, copy=False)
    move_ids = fields.One2many("stock.move", "az_count_id", "รายการปรับปรุงสต็อก", readonly=True)
    move_count = fields.Integer(compute="_compute_move_count")
    currency_id = fields.Many2one(related="company_id.currency_id")

    # สรุปผล (เหมือนท้ายชีต "กระทบยอด")
    line_count = fields.Integer("จำนวนรายการที่ต้องนับ", compute="_compute_stats")
    counted_count = fields.Integer("นับแล้ว", compute="_compute_stats")
    uncounted_count = fields.Integer("ยังไม่ได้นับ", compute="_compute_stats")
    match_count = fields.Integer("ตรงกับบัญชี", compute="_compute_stats")
    short_count = fields.Integer("ขาด (รายการ)", compute="_compute_stats")
    over_count = fields.Integer("เกิน (รายการ)", compute="_compute_stats")
    diff_line_count = fields.Integer("รายการมีผลต่าง", compute="_compute_stats")
    accuracy_pct = fields.Float("ความแม่นยำ (% รายการตรง)", compute="_compute_stats", digits=(16, 1))
    diff_qty_short = fields.Float("ขาด (จำนวน)", compute="_compute_stats", digits="Product Unit of Measure")
    diff_qty_over = fields.Float("เกิน (จำนวน)", compute="_compute_stats", digits="Product Unit of Measure")
    value_short = fields.Monetary("มูลค่าส่วนที่ขาด", compute="_compute_stats", currency_field="currency_id")
    value_over = fields.Monetary("มูลค่าส่วนที่เกิน", compute="_compute_stats", currency_field="currency_id")
    diff_value_total = fields.Monetary("ผลต่างมูลค่าสุทธิ", compute="_compute_stats", currency_field="currency_id")
    stock_value = fields.Monetary("มูลค่าสต๊อกตามบัญชี", compute="_compute_stats", currency_field="currency_id")
    missing_reason_count = fields.Integer("ผลต่างที่ยังไม่มีสาเหตุ", compute="_compute_stats")

    # ------------------------------------------------------------------
    # defaults / compute
    # ------------------------------------------------------------------
    @api.model
    def _default_warehouse(self):
        user = self.env.user
        if "allowed_warehouse_ids" in user._fields and len(user.allowed_warehouse_ids) == 1:
            return user.allowed_warehouse_ids
        return user.property_warehouse_id or False

    @api.depends("warehouse_id")
    def _compute_location_id(self):
        for rec in self:
            if rec.warehouse_id and (not rec.location_id or rec.location_id.warehouse_id != rec.warehouse_id):
                rec.location_id = rec.warehouse_id.lot_stock_id

    @api.depends("move_ids")
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)

    @api.depends("line_ids.status", "line_ids.qty_diff", "line_ids.diff_value", "line_ids.amount",
                 "line_ids.reason")
    def _compute_stats(self):
        for rec in self:
            lines = rec.line_ids
            counted = lines.filtered(lambda l: l.status != "none")
            short = lines.filtered(lambda l: l.status == "short")
            over = lines.filtered(lambda l: l.status == "over")
            rec.line_count = len(lines)
            rec.counted_count = len(counted)
            rec.uncounted_count = len(lines) - len(counted)
            rec.match_count = len(lines.filtered(lambda l: l.status == "match"))
            rec.short_count = len(short)
            rec.over_count = len(over)
            rec.diff_line_count = len(short) + len(over)
            rec.accuracy_pct = (rec.match_count * 100.0 / len(counted)) if counted else 0.0
            rec.diff_qty_short = -sum(short.mapped("qty_diff"))
            rec.diff_qty_over = sum(over.mapped("qty_diff"))
            rec.value_short = sum(short.mapped("diff_value"))
            rec.value_over = sum(over.mapped("diff_value"))
            rec.diff_value_total = rec.value_short + rec.value_over
            rec.stock_value = sum(lines.mapped("amount"))
            rec.missing_reason_count = len((short | over).filtered(lambda l: not (l.reason or "").strip()))

    @api.constrains("date_cutoff", "date_count")
    def _check_dates(self):
        for rec in self:
            if rec.date_cutoff and rec.date_count and rec.date_cutoff > rec.date_count:
                raise ValidationError(_("วันตัดยอดบัญชีต้องไม่เกินวันที่ตรวจนับจริง"))

    @api.onchange("date_count")
    def _onchange_date_count(self):
        if self.date_count and (not self.date_cutoff or self.date_cutoff > self.date_count):
            self.date_cutoff = self.date_count

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("az.stock.count") or "/"
        return super().create(vals_list)

    def unlink(self):
        if any(r.state not in ("draft", "cancel") for r in self):
            raise UserError(_("ลบได้เฉพาะใบนับที่เป็นร่างหรือยกเลิกแล้ว"))
        return super().unlink()

    def _check_state(self, states, action):
        labels = dict(STATES)
        for rec in self:
            if rec.state not in states:
                raise UserError(_("%(name)s: %(action)s ทำได้เฉพาะสถานะ %(states)s",
                                  name=rec.name, action=action,
                                  states=" / ".join(labels[s] for s in states)))

    # ------------------------------------------------------------------
    # ยอดตามบัญชี / รับ-จ่าย ระหว่างวันตัดยอดกับวันนับ
    # ------------------------------------------------------------------
    def _tz(self):
        return pytz.timezone(self.env.user.tz or "Asia/Bangkok")

    def _local_dt_utc(self, d, t):
        """วันที่ + เวลา (local) → naive UTC datetime สำหรับเทียบกับ field Datetime"""
        return self._tz().localize(datetime.combine(d, t)).astimezone(pytz.utc).replace(tzinfo=None)

    def _end_of_day_utc(self, d):
        return self._local_dt_utc(d, time(23, 59, 59))

    def _child_location_ids(self):
        self.ensure_one()
        return self.env["stock.location"].search([("id", "child_of", self.location_id.id)]).ids

    def _quant_domain(self):
        self.ensure_one()
        return [
            ("location_id", "child_of", self.location_id.id),
            ("location_id.usage", "=", "internal"),
            ("company_id", "=", self.company_id.id),
        ]

    def _quant_qty_by_product(self):
        """{product: ยอด quant ปัจจุบันรวมทุก location ลูก} (รวมที่ยอด 0)"""
        self.ensure_one()
        qty = defaultdict(float)
        for product, total in self.env["stock.quant"]._read_group(
            self._quant_domain(), ["product_id"], ["quantity:sum"]
        ):
            qty[product] += total
        return qty

    def _move_sums(self, date_from=None, date_to=None):
        """{product: [รับเข้า, จ่ายออก]} จาก stock.move.line done ของคลังนี้
        ช่วง (date_from, date_to] — None = ไม่จำกัด; move ภายในคลังเดียวกันไม่นับทั้งสองฝั่ง"""
        self.ensure_one()
        locs = self._child_location_ids()
        base = [("state", "=", "done"), ("company_id", "=", self.company_id.id)]
        if date_from:
            base.append(("date", ">", date_from))
        if date_to:
            base.append(("date", "<=", date_to))
        MoveLine = self.env["stock.move.line"]
        sums = defaultdict(lambda: [0.0, 0.0])
        for product, total in MoveLine._read_group(
            base + [("location_dest_id", "in", locs), ("location_id", "not in", locs)],
            ["product_id"], ["quantity_product_uom:sum"],
        ):
            sums[product][0] += total
        for product, total in MoveLine._read_group(
            base + [("location_id", "in", locs), ("location_dest_id", "not in", locs)],
            ["product_id"], ["quantity_product_uom:sum"],
        ):
            sums[product][1] += total
        return sums

    def _compute_balances(self):
        """{product: (ยอด ณ สิ้นวันตัดยอด, รับเข้าช่วงนับ, จ่ายออกช่วงนับ)} สำหรับทุกสินค้าที่เกี่ยวข้อง"""
        self.ensure_one()
        cutoff_end = self._end_of_day_utc(self.date_cutoff)
        count_end = self._end_of_day_utc(self.date_count)
        now_qty = self._quant_qty_by_product()
        after_cutoff = self._move_sums(date_from=cutoff_end)          # ย้อนยอดกลับไปวันตัดยอด
        between = self._move_sums(date_from=cutoff_end, date_to=count_end)
        products = set(now_qty) | set(after_cutoff) | set(between)
        result = {}
        for product in products:
            qty_in_after, qty_out_after = after_cutoff.get(product, (0.0, 0.0))
            at_cutoff = now_qty.get(product, 0.0) - qty_in_after + qty_out_after
            qty_in, qty_out = between.get(product, (0.0, 0.0))
            result[product] = (at_cutoff, qty_in, qty_out)
        return result

    @api.model
    def _line_sort_key(self, product):
        return (product.categ_id.complete_name or "", product.default_code or "", product.name or "")

    def action_generate_lines(self):
        self._check_state(("draft",), "ดึงรายการสินค้า")
        for rec in self:
            balances = rec._compute_balances()
            categs = rec.categ_ids
            if categs:
                categs = self.env["product.category"].search([("id", "child_of", categs.ids)])
            products = []
            for product, (at_cutoff, qty_in, qty_out) in balances.items():
                if not product.is_storable or not product.active:
                    continue
                if categs and product.categ_id not in categs:
                    continue
                rounding = product.uom_id.rounding
                has_qty = not float_is_zero(at_cutoff, precision_rounding=rounding) \
                    or not float_is_zero(qty_in, precision_rounding=rounding) \
                    or not float_is_zero(qty_out, precision_rounding=rounding)
                if not rec.include_zero and not has_qty:
                    continue
                products.append(product)
            if not products:
                raise UserError(_("%(name)s: ไม่พบสินค้าที่มีสต็อกใน %(loc)s",
                                  name=rec.name, loc=rec.location_id.complete_name))
            products.sort(key=self._line_sort_key)
            rec.line_ids.unlink()
            vals = []
            for seq, product in enumerate(products, 1):
                at_cutoff, qty_in, qty_out = balances[product]
                vals.append({
                    "count_id": rec.id,
                    "sequence": seq,
                    "product_id": product.id,
                    "qty_system": at_cutoff,
                    "qty_in": qty_in,
                    "qty_out": qty_out,
                    "standard_price": product.with_company(rec.company_id).standard_price,
                })
            self.env["az.stock.count.line"].create(vals)
            rec.snapshot_date = fields.Datetime.now()
        return True

    def _refresh_system_qty(self):
        """คำนวณยอดตามบัญชี/รับ/จ่าย/ต้นทุนของรายการที่มีอยู่ใหม่ (ไม่เพิ่ม/ลบรายการ)"""
        for rec in self:
            balances = rec._compute_balances()
            for line in rec.line_ids:
                at_cutoff, qty_in, qty_out = balances.get(line.product_id, (0.0, 0.0, 0.0))
                line.write({
                    "qty_system": at_cutoff,
                    "qty_in": qty_in,
                    "qty_out": qty_out,
                    "standard_price": line.product_id.with_company(rec.company_id).standard_price,
                })
            rec.snapshot_date = fields.Datetime.now()

    def action_refresh_system_qty(self):
        self._check_state(("draft", "counting", "counted"), "รีเฟรชยอดระบบ")
        self._refresh_system_qty()
        return True

    # ------------------------------------------------------------------
    # workflow
    # ------------------------------------------------------------------
    def action_start(self):
        self._check_state(("draft",), "เริ่มนับ")
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("%s: ยังไม่มีรายการสินค้า กด 'ดึงรายการสินค้า' ก่อน", rec.name))
            rec._refresh_system_qty()
            for seq, line in enumerate(rec.line_ids.sorted(lambda l: self._line_sort_key(l.product_id)), 1):
                line.sequence = seq
            rec.state = "counting"
        return True

    def action_confirm_counted(self):
        self._check_state(("counting",), "ยืนยันผลนับ")
        for rec in self:
            if not rec.line_ids.filtered("counted"):
                raise UserError(_("%s: ยังไม่ได้กรอกยอดนับเลยสักรายการ", rec.name))
            rec._refresh_system_qty()
            rec.state = "counted"
        return True

    def action_mark_rest_zero(self):
        """รายการที่ยังไม่ได้คีย์ทั้งหมด = นับได้ 0 (ใช้หลังคีย์ครบแล้ว ของที่ไม่มีในใบนับจริงคือหมด)"""
        self._check_state(("counting",), "ทำเครื่องหมายที่เหลือ = 0")
        for rec in self:
            rest = rec.line_ids.filtered(lambda l: not l.counted)
            rest.write({"qty_counted": 0.0, "counted": True})
            rec.message_post(body=_("ทำเครื่องหมายรายการที่ไม่ได้คีย์ %d รายการ = นับได้ 0", len(rest)))
        return True

    def action_back_to_counting(self):
        self._check_state(("counted",), "กลับไปแก้ยอดนับ")
        self.write({"state": "counting"})
        return True

    def action_draft(self):
        self._check_state(("counting", "counted", "cancel"), "กลับเป็นร่าง")
        self.write({"state": "draft"})
        return True

    def action_cancel(self):
        self._check_state(("draft", "counting", "counted"), "ยกเลิก")
        self.write({"state": "cancel"})
        return True

    def _check_reasons(self):
        for rec in self:
            if rec.missing_reason_count:
                raise UserError(_(
                    "%(name)s: มีรายการขาด/เกิน %(n)d รายการที่ยังไม่ได้กรอกสาเหตุของผลต่าง "
                    "(แท็บ กระทบยอด / สาเหตุผลต่าง) — ทุกผลต่างต้องมีคำอธิบายก่อนปิดใบ",
                    name=rec.name, n=rec.missing_reason_count))

    def action_close(self):
        """ปิดใบโดยไม่ปรับยอดในระบบ — ผลต่างให้แก้ที่ต้นทางด้วยเอกสารที่ถูกต้อง"""
        self._check_state(("counted",), "ปิดใบ (ไม่ปรับระบบ)")
        self._check_reasons()
        self.write({"state": "closed", "closed_by": self.env.user.id, "closed_date": fields.Datetime.now()})
        for rec in self:
            rec.message_post(body=rec._summary_html(_("ปิดใบกระทบยอด (ไม่ปรับยอดในระบบ)")))
        return True

    def _backdate_datetime(self):
        """วันนับ → datetime เที่ยงวันตาม timezone ผู้ใช้ (เก็บเป็น UTC)"""
        self.ensure_one()
        return self._local_dt_utc(self.date_count, time(12, 0))

    def action_apply(self):
        self._check_state(("counted",), "ปรับปรุงสต็อก")
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise UserError(_("ปรับปรุงสต็อกจากใบนับต้องเป็น Inventory Manager"))
        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        for rec in self:
            if rec.date_count > fields.Date.context_today(rec):
                raise UserError(_("%s: วันที่นับเป็นวันในอนาคต ปรับปรุงไม่ได้", rec.name))
            rec._refresh_system_qty()
            lines = rec.line_ids.filtered(lambda l: l.status in ("short", "over"))
            if not rec.line_ids.filtered("counted"):
                raise UserError(_("%s: ไม่มีรายการที่นับแล้ว", rec.name))
            tracked = lines.filtered(lambda l: l.product_id.tracking != "none")
            if tracked:
                raise UserError(_("สินค้าที่ติดตาม Lot/Serial ปรับจากใบนับไม่ได้: %s",
                                  ", ".join(tracked.mapped("product_id.display_name")[:10])))
            quants_to_apply = Quant.browse()
            for line in lines:
                quants = Quant.search(
                    [("product_id", "=", line.product_id.id)] + rec._quant_domain()
                ).filtered(lambda q: not q.lot_id and not q.package_id and not q.owner_id)
                locations = quants.mapped("location_id")
                if len(locations) > 1:
                    raise UserError(_(
                        "%(name)s: สินค้า %(product)s มีของอยู่หลายตำแหน่ง (%(locs)s) ต้องแยกใบนับตามตำแหน่งเก็บ",
                        name=rec.name, product=line.product_id.display_name,
                        locs=", ".join(locations.mapped("complete_name")),
                    ))
                # ปรับ "เท่าผลต่าง" บนยอดปัจจุบัน (หลังวันนับอาจมีรับ/จ่ายต่อแล้ว)
                if quants:
                    quant = quants[0]
                    quant.inventory_quantity = quant.quantity + line.qty_diff
                else:
                    quant = Quant.create({
                        "product_id": line.product_id.id,
                        "location_id": rec.location_id.id,
                        "inventory_quantity": line.qty_diff,
                    })
                quant.accounting_date = rec.date_count
                quants_to_apply |= quant
            if quants_to_apply:
                quants_to_apply.with_context(
                    inventory_name=_("ใบตรวจนับ %s", rec.name),
                    az_count_id=rec.id,
                )._apply_inventory()
                rec._stamp_move_dates()
            rec.write({
                "state": "done",
                "closed_by": self.env.user.id,
                "closed_date": fields.Datetime.now(),
            })
            rec.message_post(body=rec._summary_html(
                _("ปรับปรุงสต็อกจากใบนับ %d รายการ", len(rec.move_ids))))
        return True

    def _stamp_move_dates(self):
        """ประทับวันนับลง stock.move / move line / valuation layer (JE ใช้ accounting_date แล้ว)"""
        for rec in self:
            moves = rec.move_ids.filtered(lambda m: m.state == "done")
            if not moves or rec.date_count >= fields.Date.context_today(rec):
                continue
            dt = rec._backdate_datetime()
            moves.write({"date": dt})
            moves.move_line_ids.write({"date": dt})
            svls = moves.sudo().stock_valuation_layer_ids
            if svls:
                self.env.cr.execute(
                    "UPDATE stock_valuation_layer SET create_date = %s WHERE id IN %s",
                    (dt, tuple(svls.ids)),
                )
                svls.invalidate_recordset(["create_date"])

    def _summary_html(self, title):
        self.ensure_one()
        return Markup("<b>%s</b><br/>%s<br/>%s") % (
            escape(title),
            _("รายการ %(n)d, นับแล้ว %(c)d, ตรง %(m)d, ขาด %(s)d, เกิน %(o)d (ความแม่นยำ %(acc)s)",
              n=self.line_count, c=self.counted_count, m=self.match_count,
              s=self.short_count, o=self.over_count, acc=self._fmt_pct(self.accuracy_pct)),
            _("มูลค่าขาด %(vs)s / เกิน %(vo)s / สุทธิ %(vn)s",
              vs=self._fmt_money(self.value_short), vo=self._fmt_money(self.value_over),
              vn=self._fmt_money(self.diff_value_total)),
        )

    # ------------------------------------------------------------------
    # ปุ่ม / helper
    # ------------------------------------------------------------------
    def action_view_moves(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("รายการปรับปรุงสต็อก %s", self.name),
            "res_model": "stock.move",
            "view_mode": "list,form",
            "domain": [("az_count_id", "=", self.id)],
            "context": {"create": False},
        }

    def action_print_form(self):
        return self.env.ref("custom_stock_count.action_report_az_stock_count").report_action(self)

    def action_print_recon(self):
        return self.env.ref("custom_stock_count.action_report_az_stock_count_recon").report_action(
            self, data={"only_diff": False})

    def action_print_recon_diff(self):
        return self.env.ref("custom_stock_count.action_report_az_stock_count_recon").report_action(
            self, data={"only_diff": True})

    def action_open_import(self):
        self.ensure_one()
        self._check_state(("counting", "counted"), "นำเข้าจาก Excel")
        return {
            "type": "ir.actions.act_window",
            "name": _("นำเข้ายอดนับ / สาเหตุผลต่าง จาก Excel"),
            "res_model": "az.stock.count.import",
            "view_mode": "form",
            "target": "new",
            "context": {"default_count_id": self.id},
        }

    def action_view_lines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("รายการนับ %s", self.name),
            "res_model": "az.stock.count.line",
            "view_mode": "list",
            "domain": [("count_id", "=", self.id)],
            "context": {"group_by": "categ_name", "create": False},
        }

    @api.model
    def _fmt_qty(self, qty):
        """จำนวน: เต็ม → ไม่มีทศนิยม, ไม่เต็ม → สูงสุด 2 ตำแหน่ง"""
        if qty is None or qty is False:
            return ""
        qty = float_round(qty, precision_digits=2)
        if float_is_zero(qty - round(qty), precision_digits=2):
            return "{:,.0f}".format(qty)
        return "{:,.2f}".format(qty)

    @api.model
    def _fmt_money(self, value):
        return "{:,.2f}".format(value or 0.0)

    @api.model
    def _fmt_pct(self, value):
        return "{:,.1f}%".format(value or 0.0)

    @api.model
    def _fmt_date(self, d):
        return d.strftime("%d/%m/%Y") if d else ""

    def _show_system_qty(self):
        """ใบตรวจนับแสดงยอดตามบัญชีหรือไม่: ปิดเฉพาะตอน blind และยังนับไม่เสร็จ"""
        self.ensure_one()
        return (not self.blind) or self.state in ("counted", "closed", "done")

    def _show_counted(self):
        self.ensure_one()
        return self.state in ("counting", "counted", "closed", "done") and bool(self.line_ids.filtered("counted"))

    def _report_groups(self, lines=None):
        """[(ชื่อหมวด, [lines...]), ...] เรียงตามลำดับในใบ"""
        self.ensure_one()
        groups = []
        for line in (lines if lines is not None else self.line_ids).sorted(lambda l: (l.sequence, l.id)):
            key = line.categ_name or ""
            if not groups or groups[-1][0] != key:
                groups.append((key, []))
            groups[-1][1].append(line)
        return groups

    def _count_type_label(self):
        self.ensure_one()
        return dict(COUNT_TYPES).get(self.count_type, "")

    def _period_label(self):
        """ข้อความช่วงรับ/จ่าย เช่น "01/10/2026 ถึง 08/10/2026" (ว่าง = นับวันเดียวกับตัดยอด)"""
        self.ensure_one()
        if self.date_cutoff >= self.date_count:
            return ""
        start = fields.Date.add(self.date_cutoff, days=1)
        return "%s ถึง %s" % (self._fmt_date(start), self._fmt_date(self.date_count))

    def _snapshot_local(self):
        self.ensure_one()
        if not self.snapshot_date:
            return ""
        return fields.Datetime.context_timestamp(self, self.snapshot_date).strftime("%d/%m/%Y %H:%M")


class StockCountLine(models.Model):
    _name = "az.stock.count.line"
    _description = "รายการตรวจนับสต็อก"
    _order = "count_id desc, sequence, id"

    count_id = fields.Many2one("az.stock.count", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="count_id.company_id", store=True)
    warehouse_id = fields.Many2one(related="count_id.warehouse_id", store=True, string="สาขา / คลัง")
    date_count = fields.Date(related="count_id.date_count", store=True, string="วันที่นับ")
    state = fields.Selection(related="count_id.state", store=True, string="สถานะใบนับ")
    sequence = fields.Integer("ลำดับ", default=0)
    product_id = fields.Many2one(
        "product.product", "สินค้า", required=True, ondelete="restrict",
        domain="[('is_storable', '=', True)]",
    )
    default_code = fields.Char(related="product_id.default_code", string="รหัสสินค้า")
    categ_name = fields.Char(
        related="product_id.categ_id.complete_name", string="หมวดสินค้า", store=True
    )
    uom_id = fields.Many2one(related="product_id.uom_id", string="หน่วย")
    qty_system = fields.Float("ยอดตามบัญชี ณ วันตัดยอด", digits="Product Unit of Measure", readonly=True)
    qty_in = fields.Float("+ รับเข้า", digits="Product Unit of Measure", readonly=True,
                          help="รับเข้าคลังนี้หลังวันตัดยอดถึงสิ้นวันนับ (จากประวัติการเคลื่อนไหว)")
    qty_out = fields.Float("- จ่ายออก", digits="Product Unit of Measure", readonly=True,
                           help="จ่ายออกจากคลังนี้หลังวันตัดยอดถึงสิ้นวันนับ")
    qty_expected = fields.Float("ยอดที่ควรมี ณ วันนับ", digits="Product Unit of Measure",
                                compute="_compute_diff", store=True)
    qty_counted = fields.Float("ยอดตรวจนับได้", digits="Product Unit of Measure")
    counted = fields.Boolean("นับแล้ว", default=False)
    qty_diff = fields.Float("ผลต่างจำนวน", digits="Product Unit of Measure", compute="_compute_diff", store=True)
    diff_pct = fields.Float("ผลต่าง %", digits=(16, 1), compute="_compute_diff", store=True)
    standard_price = fields.Float("ราคาทุน/หน่วย", digits="Product Price", readonly=True)
    amount = fields.Float("มูลค่าตามบัญชี", digits="Product Price", compute="_compute_diff", store=True)
    diff_value = fields.Float("ผลต่างมูลค่า", digits="Product Price", compute="_compute_diff", store=True)
    status = fields.Selection(LINE_STATUS, "สถานะ", compute="_compute_diff", store=True)
    note = fields.Char("หมายเหตุ")
    # หมายเหตุผลต่าง (ชีต "หมายเหตุผลต่าง")
    reason = fields.Char("สาเหตุของผลต่าง")
    ref_doc = fields.Char("เอกสาร / หลักฐานอ้างอิง")
    responsible = fields.Char("ผู้รับผิดชอบ")
    action_taken = fields.Char("การดำเนินการแก้ไขที่ต้นทาง")
    date_resolved = fields.Date("วันที่แล้วเสร็จ")

    _sql_constraints = [
        ("product_uniq", "unique(count_id, product_id)", "สินค้าซ้ำในใบนับเดียวกัน"),
    ]

    @api.depends("qty_system", "qty_in", "qty_out", "qty_counted", "counted", "standard_price")
    def _compute_diff(self):
        for line in self:
            expected = line.qty_system + line.qty_in - line.qty_out
            line.qty_expected = expected
            line.amount = line.qty_system * (line.standard_price or 0.0)
            if not line.counted:
                line.qty_diff = 0.0
                line.diff_pct = 0.0
                line.diff_value = 0.0
                line.status = "none"
                continue
            diff = line.qty_counted - expected
            rounding = line.product_id.uom_id.rounding or 0.01
            line.qty_diff = diff
            line.diff_pct = (diff / expected * 100.0) if not float_is_zero(expected, precision_rounding=rounding) else 0.0
            line.diff_value = diff * (line.standard_price or 0.0)
            cmp = float_compare(diff, 0.0, precision_rounding=rounding)
            line.status = "match" if cmp == 0 else ("over" if cmp > 0 else "short")

    @api.onchange("qty_counted")
    def _onchange_qty_counted(self):
        """พิมพ์ตัวเลขในช่องนับ (รวม 0) = นับแล้ว — ฝั่งหน้าจอทันที ไม่ต้องรอ write
        หมายเหตุ: พิมพ์ 0 ทับ 0.00 เดิม client ไม่ส่ง onchange/write (ไม่มีการเปลี่ยนค่า)
        ต้องติ๊กช่อง 'นับแล้ว' เอง หรือใช้ปุ่ม 'ที่เหลือ = 0' บนหัวใบ"""
        for line in self:
            if line.count_id.state in ("counting", "counted") and not line.counted:
                line.counted = True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("qty_counted") and "counted" not in vals:
                vals["counted"] = True
            if vals.get("product_id") and vals.get("count_id") and "standard_price" not in vals:
                count = self.env["az.stock.count"].browse(vals["count_id"])
                product = self.env["product.product"].browse(vals["product_id"])
                if "qty_system" not in vals:
                    at_cutoff, qty_in, qty_out = count._compute_balances().get(product, (0.0, 0.0, 0.0))
                    vals.update({"qty_system": at_cutoff, "qty_in": qty_in, "qty_out": qty_out})
                vals["standard_price"] = product.with_company(count.company_id).standard_price
        return super().create(vals_list)

    def write(self, vals):
        if "qty_counted" in vals and "counted" not in vals:
            vals["counted"] = True
        return super().write(vals)

    def unlink(self):
        if any(l.count_id.state not in ("draft", "cancel") for l in self):
            raise UserError(_("ลบรายการได้เฉพาะใบนับที่เป็นร่าง"))
        return super().unlink()

    def action_clear_count(self):
        self.write({"qty_counted": 0.0, "counted": False})
        return True

    def _status_label(self):
        self.ensure_one()
        return dict(LINE_STATUS).get(self.status, "")
