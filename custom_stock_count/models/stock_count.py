# -*- coding: utf-8 -*-
"""ใบตรวจนับสต็อก (Physical Count Sheet) — จบในจอเดียว

ขั้นตอน:
  ร่าง (draft)      : เลือกสาขา/คลัง → "ดึงรายการสินค้า" (snapshot ยอดคงเหลือ + ต้นทุน) → พิมพ์/Export แบบฟอร์ม
  กำลังนับ (counting): ล็อกรายการ, คีย์ยอดนับในจอ หรือนำเข้า Excel ที่กรอกแล้ว
  นับแล้ว (counted)  : ตรวจผลต่าง (จำนวน + มูลค่า) ก่อนอนุมัติ
  ปรับปรุงแล้ว (done): สร้าง Inventory Adjustment ผ่าน stock.quant (inventory_mode) ลงวันที่ = วันนับ
                       → stock.move ผูก az_count_id กลับมาที่ใบนี้

* ยอดระบบ (qty_system) = ยอดรวมทุก location ลูกใต้ location ที่เลือก ณ เวลา snapshot
  ตอนปรับปรุงจะรีเฟรชยอดระบบอีกครั้งเพื่อให้ผลต่างที่เห็นตรงกับที่ Odoo บันทึกจริง
* สินค้า 1 ตัวที่มีของอยู่หลาย location ลูก → ปรับปรุงไม่ได้ ต้องแยกใบนับตาม location
* ปรับปรุงสต็อกต้องเป็น Inventory Manager (stock.group_stock_manager)
"""
from collections import defaultdict
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero, float_round

COUNT_TYPES = [("monthly", "ประจำเดือน"), ("yearly", "ประจำปี"), ("spot", "สุ่มตรวจ")]
STATES = [
    ("draft", "ร่าง"),
    ("counting", "กำลังนับ"),
    ("counted", "นับแล้ว รอปรับปรุง"),
    ("done", "ปรับปรุงแล้ว"),
    ("cancel", "ยกเลิก"),
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
    date_count = fields.Date(
        "วันที่นับ", required=True, default=fields.Date.context_today, tracking=True,
    )
    snapshot_date = fields.Datetime("ยอดคงเหลือ ณ", readonly=True, copy=False)
    count_type = fields.Selection(COUNT_TYPES, "รอบการนับ", required=True, default="monthly", tracking=True)
    counter1 = fields.Char("ผู้นับคนที่ 1")
    counter2 = fields.Char("ผู้นับคนที่ 2")
    checker = fields.Char("ผู้ทาน / หัวหน้าคลัง")
    approver = fields.Char("ผู้อนุมัติ")
    blind = fields.Boolean(
        "แบบฟอร์มไม่แสดงยอดคงเหลือ (นับแบบไม่เห็นยอด)", default=True,
        help="ติ๊ก = PDF/Excel ที่ส่งให้สาขาจะเว้นคอลัมน์ยอดคงเหลือไว้ ให้นับจริงก่อนแล้วค่อยเทียบ",
    )
    include_zero = fields.Boolean(
        "รวมสินค้าที่ยอดเป็น 0 แต่เคยมีในคลัง", default=False,
        help="ติ๊ก = เอาสินค้าที่เคยรับเข้าคลังนี้แต่ตอนนี้ยอด 0 ใส่ในใบนับด้วย (เผื่อนับเจอของที่ระบบว่าหมด)",
    )
    categ_ids = fields.Many2many(
        "product.category", string="เฉพาะหมวดสินค้า",
        help="ว่าง = ทุกหมวด; เลือกแล้วจะดึงเฉพาะสินค้าในหมวดนั้น (รวมหมวดย่อย)",
    )
    state = fields.Selection(STATES, "สถานะ", default="draft", required=True, tracking=True, copy=False)
    line_ids = fields.One2many("az.stock.count.line", "count_id", "รายการนับ", copy=True)
    note = fields.Text("หมายเหตุ")
    user_id = fields.Many2one("res.users", "ผู้สร้าง", default=lambda self: self.env.user, readonly=True)
    applied_by = fields.Many2one("res.users", "ผู้ปรับปรุง", readonly=True, copy=False)
    applied_date = fields.Datetime("ปรับปรุงเมื่อ", readonly=True, copy=False)
    move_ids = fields.One2many("stock.move", "az_count_id", "รายการปรับปรุงสต็อก", readonly=True)
    move_count = fields.Integer(compute="_compute_move_count")

    line_count = fields.Integer("จำนวนรายการ", compute="_compute_stats")
    counted_count = fields.Integer("นับแล้ว", compute="_compute_stats")
    uncounted_count = fields.Integer("ยังไม่นับ", compute="_compute_stats")
    diff_line_count = fields.Integer("รายการมีผลต่าง", compute="_compute_stats")
    diff_qty_short = fields.Float("ขาด (จำนวน)", compute="_compute_stats", digits="Product Unit of Measure")
    diff_qty_over = fields.Float("เกิน (จำนวน)", compute="_compute_stats", digits="Product Unit of Measure")
    diff_value_total = fields.Monetary("ผลต่างสุทธิ (มูลค่า)", compute="_compute_stats", currency_field="currency_id")
    currency_id = fields.Many2one(related="company_id.currency_id")

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

    @api.depends("line_ids.counted", "line_ids.qty_diff", "line_ids.diff_value")
    def _compute_stats(self):
        for rec in self:
            lines = rec.line_ids
            counted = lines.filtered("counted")
            diff_lines = counted.filtered(
                lambda l: not float_is_zero(l.qty_diff, precision_rounding=l.product_id.uom_id.rounding or 0.01)
            )
            rec.line_count = len(lines)
            rec.counted_count = len(counted)
            rec.uncounted_count = len(lines) - len(counted)
            rec.diff_line_count = len(diff_lines)
            rec.diff_qty_short = -sum(l.qty_diff for l in diff_lines if l.qty_diff < 0)
            rec.diff_qty_over = sum(l.qty_diff for l in diff_lines if l.qty_diff > 0)
            rec.diff_value_total = sum(diff_lines.mapped("diff_value"))

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
    # ดึงรายการ / snapshot ยอดระบบ
    # ------------------------------------------------------------------
    def _quant_domain(self):
        self.ensure_one()
        return [
            ("location_id", "child_of", self.location_id.id),
            ("location_id.usage", "=", "internal"),
            ("company_id", "=", self.company_id.id),
        ]

    def _system_qty_by_product(self):
        """{product: ยอดรวมทุก location ลูก} จาก stock.quant (รวมที่ยอด 0 ด้วย)"""
        self.ensure_one()
        qty = defaultdict(float)
        groups = self.env["stock.quant"]._read_group(
            self._quant_domain(), ["product_id"], ["quantity:sum"]
        )
        for product, total in groups:
            qty[product] += total
        return qty

    @api.model
    def _line_sort_key(self, product):
        return (product.categ_id.complete_name or "", product.default_code or "", product.name or "")

    def action_generate_lines(self):
        self._check_state(("draft",), "ดึงรายการสินค้า")
        for rec in self:
            qty_map = rec._system_qty_by_product()
            categs = rec.categ_ids
            if categs:
                categs = self.env["product.category"].search([("id", "child_of", categs.ids)])
            products = []
            for product, qty in qty_map.items():
                if not product.is_storable or not product.active:
                    continue
                if categs and product.categ_id not in categs:
                    continue
                if not rec.include_zero and float_is_zero(qty, precision_rounding=product.uom_id.rounding):
                    continue
                products.append(product)
            if not products:
                raise UserError(_("%(name)s: ไม่พบสินค้าที่มีสต็อกใน %(loc)s",
                                  name=rec.name, loc=rec.location_id.complete_name))
            products.sort(key=self._line_sort_key)
            rec.line_ids.unlink()
            vals = []
            for seq, product in enumerate(products, 1):
                vals.append({
                    "count_id": rec.id,
                    "sequence": seq,
                    "product_id": product.id,
                    "qty_system": qty_map[product],
                    "standard_price": product.with_company(rec.company_id).standard_price,
                })
            self.env["az.stock.count.line"].create(vals)
            rec.snapshot_date = fields.Datetime.now()
        return True

    def _refresh_system_qty(self):
        """อัปเดตยอดระบบ/ต้นทุนของรายการที่มีอยู่ให้เป็นปัจจุบัน (ไม่เพิ่ม/ลบรายการ)"""
        for rec in self:
            qty_map = rec._system_qty_by_product()
            for line in rec.line_ids:
                line.write({
                    "qty_system": qty_map.get(line.product_id, 0.0),
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

    def _backdate_datetime(self):
        """วันนับ → datetime เที่ยงวันตาม timezone ผู้ใช้ (เก็บเป็น UTC)"""
        self.ensure_one()
        tz = pytz.timezone(self.env.user.tz or "Asia/Bangkok")
        local_noon = tz.localize(datetime.combine(self.date_count, time(12, 0)))
        return local_noon.astimezone(pytz.utc).replace(tzinfo=None)

    def action_apply(self):
        self._check_state(("counted",), "ปรับปรุงสต็อก")
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise UserError(_("ปรับปรุงสต็อกจากใบนับต้องเป็น Inventory Manager"))
        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        for rec in self:
            if rec.date_count > fields.Date.context_today(rec):
                raise UserError(_("%s: วันที่นับเป็นวันในอนาคต ปรับปรุงไม่ได้", rec.name))
            rec._refresh_system_qty()
            lines = rec.line_ids.filtered("counted")
            if not lines:
                raise UserError(_("%s: ไม่มีรายการที่นับแล้ว", rec.name))
            tracked = lines.filtered(lambda l: l.product_id.tracking != "none")
            if tracked:
                raise UserError(_("สินค้าที่ติดตาม Lot/Serial ปรับจากใบนับไม่ได้: %s",
                                  ", ".join(tracked.mapped("product_id.display_name")[:10])))
            quants_to_apply = Quant.browse()
            for line in lines:
                rounding = line.product_id.uom_id.rounding
                if float_compare(line.qty_counted, line.qty_system, precision_rounding=rounding) == 0:
                    continue
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
                if quants:
                    quant = quants[0]
                    others = sum(quants[1:].mapped("quantity"))
                    quant.inventory_quantity = line.qty_counted - others
                else:
                    quant = Quant.create({
                        "product_id": line.product_id.id,
                        "location_id": rec.location_id.id,
                        "inventory_quantity": line.qty_counted,
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
                "applied_by": self.env.user.id,
                "applied_date": fields.Datetime.now(),
            })
            rec.message_post(body=_(
                "ปรับปรุงสต็อกจากใบนับ: %(n)d รายการ (ขาด %(short)s / เกิน %(over)s, มูลค่าสุทธิ %(value)s)",
                n=len(rec.move_ids), short=rec._fmt_qty(rec.diff_qty_short),
                over=rec._fmt_qty(rec.diff_qty_over),
                value="{:,.2f}".format(rec.diff_value_total),
            ))
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

    def action_open_import(self):
        self.ensure_one()
        self._check_state(("counting",), "นำเข้ายอดนับจาก Excel")
        return {
            "type": "ir.actions.act_window",
            "name": _("นำเข้ายอดนับจาก Excel"),
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

    def _show_system_qty(self):
        """แบบฟอร์มแสดงยอดคงเหลือหรือไม่: ปิดเฉพาะตอน blind และยังนับไม่เสร็จ"""
        self.ensure_one()
        return (not self.blind) or self.state in ("counted", "done")

    def _show_counted(self):
        self.ensure_one()
        return self.state in ("counting", "counted", "done") and bool(self.line_ids.filtered("counted"))

    def _report_groups(self):
        """[(ชื่อหมวด, [lines...]), ...] เรียงตามลำดับในใบ"""
        self.ensure_one()
        groups = []
        for line in self.line_ids.sorted(lambda l: (l.sequence, l.id)):
            key = line.categ_name or ""
            if not groups or groups[-1][0] != key:
                groups.append((key, []))
            groups[-1][1].append(line)
        return groups

    def _count_type_label(self):
        self.ensure_one()
        return dict(COUNT_TYPES).get(self.count_type, "")

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
    qty_system = fields.Float("ยอดคงเหลือ (ระบบ)", digits="Product Unit of Measure", readonly=True)
    qty_counted = fields.Float("ยอดตรวจนับ", digits="Product Unit of Measure")
    counted = fields.Boolean("นับแล้ว", default=False)
    qty_diff = fields.Float(
        "ผลต่าง", digits="Product Unit of Measure", compute="_compute_diff", store=True
    )
    standard_price = fields.Float("ต้นทุน/หน่วย", digits="Product Price", readonly=True)
    diff_value = fields.Float("ผลต่าง (มูลค่า)", digits="Product Price", compute="_compute_diff", store=True)
    note = fields.Char("หมายเหตุ")

    _sql_constraints = [
        ("product_uniq", "unique(count_id, product_id)", "สินค้าซ้ำในใบนับเดียวกัน"),
    ]

    @api.depends("qty_system", "qty_counted", "counted", "standard_price")
    def _compute_diff(self):
        for line in self:
            diff = (line.qty_counted - line.qty_system) if line.counted else 0.0
            line.qty_diff = diff
            line.diff_value = diff * (line.standard_price or 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("qty_counted") and "counted" not in vals:
                vals["counted"] = True
            if vals.get("product_id") and vals.get("count_id") and "standard_price" not in vals:
                count = self.env["az.stock.count"].browse(vals["count_id"])
                product = self.env["product.product"].browse(vals["product_id"])
                if "qty_system" not in vals:
                    vals["qty_system"] = count._system_qty_by_product().get(product, 0.0)
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
