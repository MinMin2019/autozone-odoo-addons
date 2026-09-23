# -*- coding: utf-8 -*-
"""ใบเบิกใช้วัสดุ (สาขา) — จอเดียวครอบ operation type CONS ของ custom_branch_consumption

ผู้ใช้เลือกสาขา (ระบบเดาให้จากคลังของผู้ใช้) ใส่สินค้า/จำนวน แล้วกด "บันทึกเบิก"
ระบบสร้างใบ CONS ของสาขานั้น + validate ทันที → ต้นทุนลงบัญชีค่าใช้จ่าย + สาขา (analytic)
ตาม logic เดิมของ custom_branch_consumption ทุกประการ

กติกา
  * เบิกเกินของคงเหลือที่สาขาไม่ได้ (กันสต็อกติดลบ) — ให้ปรับสต็อก/รับของก่อน
  * วันที่ย้อนหลังได้ ถ้ามี custom_stock_backdate จะประทับวันนั้นลง JE ให้เอง
  * ใบที่เบิกแล้วแก้ไม่ได้ ถ้าคืนของให้กด "เบิกคืน" (return ใบ CONS ตามมาตรฐาน)
"""
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

CONS = "CONS"


class BranchConsumption(models.Model):
    _name = "az.branch.consumption"
    _description = "ใบเบิกใช้วัสดุ"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char("เลขที่", default="/", readonly=True, copy=False)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, readonly=True
    )
    allowed_warehouse_ids = fields.Many2many(
        "stock.warehouse", compute="_compute_allowed_warehouse_ids"
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse", "สาขา / คลังที่เบิก", required=True, tracking=True,
        default=lambda self: self._default_warehouse(),
        domain="[('id', 'in', allowed_warehouse_ids)]",
    )
    picking_type_id = fields.Many2one(
        "stock.picking.type", compute="_compute_picking_type", string="ประเภทใบเบิก"
    )
    location_id = fields.Many2one(
        "stock.location", compute="_compute_picking_type", string="จากคลัง"
    )
    date = fields.Date("วันที่เบิก", default=fields.Date.context_today, required=True, tracking=True)
    requester = fields.Char(
        "ผู้เบิก", default=lambda self: self.env.user.name, tracking=True,
        help="ชื่อคนที่มาเบิกของ (พิมพ์ได้อิสระ)",
    )
    purpose = fields.Char(
        "เบิกไปใช้กับ", tracking=True,
        help="เช่น งานซ่อมทะเบียน กข-1234 / ทำความสะอาดร้าน",
    )
    note = fields.Text("หมายเหตุ")
    user_id = fields.Many2one(
        "res.users", "ผู้บันทึก", default=lambda self: self.env.user, readonly=True
    )
    line_ids = fields.One2many(
        "az.branch.consumption.line", "consumption_id", "รายการสินค้า", copy=True
    )
    picking_ids = fields.One2many("stock.picking", "az_consumption_id", "ใบ CONS", copy=False)
    picking_id = fields.Many2one("stock.picking", "ใบเบิก (CONS)", compute="_compute_pickings")
    picking_count = fields.Integer(compute="_compute_pickings")
    state = fields.Selection(
        [
            ("draft", "ร่าง"),
            ("confirmed", "รอตัดสต็อก"),
            ("done", "เบิกแล้ว"),
            ("cancel", "ยกเลิก"),
        ],
        "สถานะ", default="draft", compute="_compute_state", store=True, tracking=True, copy=False,
    )
    cancelled = fields.Boolean(copy=False)
    qty_total = fields.Float("จำนวนรวม", compute="_compute_totals", digits="Product Unit of Measure")
    has_shortage = fields.Boolean(compute="_compute_totals")
    can_edit = fields.Boolean(compute="_compute_permissions")

    # ------------------------------------------------------------------
    # defaults / helpers
    # ------------------------------------------------------------------
    def _cons_type_domain(self, warehouse=None):
        domain = [
            ("sequence_code", "=", CONS),
            ("company_id", "=", self.env.company.id),
            ("active", "=", True),
        ]
        if warehouse:
            domain.append(("warehouse_id", "=", warehouse.id))
        return domain

    def _user_can_use_warehouse(self, warehouse):
        """ผู้ใช้คนนี้เบิกแทนคลังนี้ได้ไหม — ลำดับการเช็ค
        1. custom_warehouse_scope (ถ้าติดตั้ง): unrestricted = ทุกคลัง,
           Allowed Warehouses ไม่ว่าง = เฉพาะที่กำหนด
        2. Default Warehouse ในโปรไฟล์ผู้ใช้ (Preferences) = เฉพาะคลังนั้น
        3. ไม่ได้กำหนดอะไรเลย = ทำได้ทุกคลัง (ช่วงยังไม่ได้แบ่งสิทธิ์)"""
        user = self.env.user
        if "allowed_warehouse_ids" in user._fields:
            if user.warehouse_unrestricted:
                return True
            if user.allowed_warehouse_ids:
                return warehouse in user.allowed_warehouse_ids
        default_wh = user.with_company(self.env.company).property_warehouse_id
        return not default_wh or default_wh == warehouse

    def _allowed_warehouses(self):
        types = self.env["stock.picking.type"].sudo().search(self._cons_type_domain())
        return types.warehouse_id.filtered(self._user_can_use_warehouse)

    @api.model
    def _default_warehouse(self):
        allowed = self._allowed_warehouses()
        if len(allowed) == 1:
            return allowed
        default_wh = self.env.user.with_company(self.env.company).property_warehouse_id
        if default_wh and default_wh in allowed:
            return default_wh
        return self.env["stock.warehouse"]

    def _local_tz(self):
        return pytz.timezone(
            self.env.context.get("tz") or self.env.user.tz
            or self.company_id.partner_id.tz or "Asia/Bangkok"
        )

    # ------------------------------------------------------------------
    # computes
    # ------------------------------------------------------------------
    # depends company_id ด้วย: compute ที่ไม่มี field depends จะไม่ถูกส่งกลับใน onchange
    # ของ record ใหม่ → หน้าเว็บได้ลิสต์ว่าง → domain สาขาไม่มีตัวเลือก (บั๊ก 23 ก.ย. 2026)
    @api.depends("company_id")
    @api.depends_context("uid", "company")
    def _compute_allowed_warehouse_ids(self):
        allowed = self._allowed_warehouses()
        for rec in self:
            rec.allowed_warehouse_ids = allowed

    @api.depends("warehouse_id")
    def _compute_picking_type(self):
        PickingType = self.env["stock.picking.type"].sudo()
        for rec in self:
            rec.picking_type_id = (
                PickingType.search(rec._cons_type_domain(rec.warehouse_id), limit=1)
                if rec.warehouse_id else PickingType
            )
            rec.location_id = rec.picking_type_id.default_location_src_id

    @api.depends("picking_ids", "picking_ids.state")
    def _compute_pickings(self):
        for rec in self:
            pickings = rec.sudo().picking_ids
            rec.picking_count = len(pickings)
            rec.picking_id = pickings.filtered(lambda p: not p.return_id)[:1]

    @api.depends("picking_ids", "picking_ids.state", "cancelled")
    def _compute_state(self):
        for rec in self:
            if rec.cancelled:
                rec.state = "cancel"
                continue
            picking = rec.sudo().picking_ids.filtered(lambda p: not p.return_id)[:1]
            if not picking:
                rec.state = "draft"
            elif picking.state == "done":
                rec.state = "done"
            elif picking.state == "cancel":
                rec.state = "cancel"
            else:
                rec.state = "confirmed"

    @api.depends("line_ids.product_uom_qty", "line_ids.shortage")
    def _compute_totals(self):
        for rec in self:
            rec.qty_total = sum(rec.line_ids.mapped("product_uom_qty"))
            rec.has_shortage = any(rec.line_ids.mapped("shortage"))

    @api.depends("state", "warehouse_id")
    @api.depends_context("uid")
    def _compute_permissions(self):
        for rec in self:
            rec.can_edit = rec.state == "draft" and (
                not rec.warehouse_id or rec._user_can_use_warehouse(rec.warehouse_id)
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("az.branch.consumption") or "/"
        return super().create(vals_list)

    def write(self, vals):
        locked = {"warehouse_id", "line_ids", "date"}
        if locked & set(vals) and any(r.state != "draft" for r in self):
            raise UserError(
                _("ใบเบิกที่ตัดสต็อกแล้วแก้สาขา/วันที่/รายการไม่ได้ — ถ้าเบิกผิดให้กด 'เบิกคืน'")
            )
        return super().write(vals)

    def unlink(self):
        if any(r.state not in ("draft", "cancel") for r in self):
            raise UserError(_("ลบได้เฉพาะใบเบิกสถานะร่างหรือยกเลิก"))
        return super().unlink()

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def _check_before_consume(self):
        self.ensure_one()
        if not self._user_can_use_warehouse(self.warehouse_id):
            raise UserError(
                _("เฉพาะผู้ใช้ของ %s เท่านั้นที่เบิกของจากคลังนี้ได้") % self.warehouse_id.name
            )
        if not self.picking_type_id:
            raise UserError(
                _("คลัง %s ยังไม่มีประเภทใบเบิก 'เบิกใช้วัสดุ' (CONS) — แจ้ง IT ตั้งค่าคลังก่อน")
                % self.warehouse_id.name
            )
        lines = self.line_ids.filtered(lambda l: l.product_uom_qty > 0)
        if not lines:
            raise UserError(_("กรุณาใส่รายการสินค้าอย่างน้อย 1 บรรทัด"))
        if len(lines.mapped("product_id")) != len(lines):
            raise UserError(_("มีสินค้าซ้ำกันในใบเดียว กรุณารวมเป็นบรรทัดเดียว"))
        tracked = lines.filtered(lambda l: l.product_id.tracking != "none")
        if tracked:
            raise UserError(
                _("สินค้าที่ต้องระบุล็อต/ซีเรียล เบิกผ่านจอนี้ไม่ได้ (%s) — "
                  "ใช้ใบเบิกมาตรฐานใน Inventory Overview")
                % ", ".join(tracked.product_id.mapped("display_name"))
            )
        if self.date > fields.Date.context_today(self):
            raise UserError(_("วันที่เบิกเป็นอนาคตไม่ได้"))
        short = lines.filtered("shortage")
        if short:
            raise UserError(
                _("ของที่ %s ไม่พอเบิก:\n%s\n\nกรุณารับของเข้าคลัง/ปรับสต็อกก่อน หรือลดจำนวนตามที่มี")
                % (
                    self.warehouse_id.name,
                    "\n".join(
                        "  • %s  มี %s  จะเบิก %s"
                        % (l.product_id.display_name, l.qty_available, l.product_uom_qty)
                        for l in short
                    ),
                )
            )
        return lines

    def _prepare_picking_vals(self, lines):
        ptype = self.picking_type_id
        src = ptype.default_location_src_id
        dest = ptype.default_location_dest_id
        vals = {
            "picking_type_id": ptype.id,
            "location_id": src.id,
            "location_dest_id": dest.id,
            "origin": self.name,
            "scheduled_date": fields.Datetime.now(),
            "company_id": self.company_id.id,
            "az_consumption_id": self.id,
            "note": self.note or False,
            "move_ids": [
                (0, 0, {
                    "name": line.product_id.display_name,
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.product_uom_qty,
                    "product_uom": line.product_uom_id.id,
                    "location_id": src.id,
                    "location_dest_id": dest.id,
                    "company_id": self.company_id.id,
                })
                for line in lines
            ],
        }
        # วันที่ย้อนหลัง: ให้ custom_stock_backdate ประทับลง JE (ถ้าติดตั้ง)
        if (
            "backdate" in self.env["stock.picking"]._fields
            and self.date < fields.Date.context_today(self)
        ):
            local_noon = self._local_tz().localize(datetime.combine(self.date, time(12, 0)))
            vals["backdate"] = local_noon.astimezone(pytz.utc).replace(tzinfo=None)
        return vals

    def action_consume(self):
        """สร้างใบ CONS + validate ทันที = ตัดสต็อกและลงบัญชีค่าใช้จ่ายของสาขา"""
        for rec in self:
            if rec.state != "draft":
                continue
            lines = rec._check_before_consume()
            picking = self.env["stock.picking"].create(rec._prepare_picking_vals(lines))
            picking.action_confirm()
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            res = picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
            if picking.state != "done":
                raise UserError(
                    _("ตัดสต็อกไม่สำเร็จ (ใบ %s สถานะ %s) — ติดต่อ IT")
                    % (picking.name, picking.state)
                )
            rec.invalidate_recordset(["picking_ids"])
            rec.message_post(body=_("ตัดสต็อกแล้ว: ใบ %s") % picking.name)
            if isinstance(res, dict) and len(self) == 1:
                return res
        return True

    def action_return(self):
        """เบิกคืน = เปิด wizard Return ของใบ CONS (ของกลับเข้าคลัง + กลับรายการค่าใช้จ่าย)"""
        self.ensure_one()
        if self.state != "done" or not self.picking_id:
            raise UserError(_("เบิกคืนได้เฉพาะใบที่ตัดสต็อกแล้ว"))
        action = self.env["ir.actions.act_window"]._for_xml_id("stock.act_stock_return_picking")
        action["context"] = {
            "active_id": self.picking_id.id,
            "active_ids": self.picking_id.ids,
            "active_model": "stock.picking",
        }
        return action

    def action_view_pickings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("ใบเบิกของ %s") % self.name,
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("az_consumption_id", "=", self.id)],
            "context": {"create": False},
        }

    def action_cancel(self):
        for rec in self:
            if rec.state == "done":
                raise UserError(
                    _("ใบนี้ตัดสต็อกไปแล้ว ยกเลิกไม่ได้ — ให้กด 'เบิกคืน' เพื่อรับของกลับ")
                )
            if rec.state == "cancel":
                continue
            pickings = rec.sudo().picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
            pickings.action_cancel()
            rec.write({"cancelled": True})
        return True

    def action_draft(self):
        for rec in self:
            if rec.state != "cancel":
                raise UserError(_("กลับเป็นร่างได้เฉพาะใบที่ยกเลิกแล้ว"))
            rec.sudo().picking_ids.write({"az_consumption_id": False})
            rec.write({"cancelled": False})
        return True


class BranchConsumptionLine(models.Model):
    _name = "az.branch.consumption.line"
    _description = "รายการใบเบิกใช้วัสดุ"
    _order = "consumption_id, sequence, id"

    consumption_id = fields.Many2one(
        "az.branch.consumption", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        "product.product", "สินค้า", required=True,
        domain="[('is_storable', '=', True)]",
    )
    product_uom_id = fields.Many2one("uom.uom", "หน่วย", related="product_id.uom_id", readonly=True)
    product_uom_qty = fields.Float(
        "จำนวนเบิก", digits="Product Unit of Measure", required=True, default=1.0
    )
    qty_available = fields.Float(
        "คงเหลือที่สาขา", compute="_compute_qty_available", digits="Product Unit of Measure"
    )
    shortage = fields.Boolean(compute="_compute_qty_available")
    qty_done = fields.Float(
        "เบิกแล้ว (สุทธิ)", compute="_compute_qty_done", digits="Product Unit of Measure"
    )
    state = fields.Selection(related="consumption_id.state")
    company_id = fields.Many2one(related="consumption_id.company_id")

    _sql_constraints = [
        ("qty_positive", "CHECK(product_uom_qty > 0)", "จำนวนต้องมากกว่า 0"),
    ]

    @api.depends("product_id", "product_uom_qty", "consumption_id.location_id", "consumption_id.state")
    def _compute_qty_available(self):
        for line in self:
            loc = line.consumption_id.location_id
            if line.product_id and loc:
                line.qty_available = line.product_id.sudo().with_context(
                    location=loc.id
                ).qty_available
            else:
                line.qty_available = 0.0
            rounding = line.product_uom_id.rounding or 0.01
            line.shortage = (
                line.state == "draft"
                and bool(line.product_id)
                and float_compare(
                    line.product_uom_qty, line.qty_available, precision_rounding=rounding
                ) > 0
            )

    @api.depends(
        "consumption_id.picking_ids.state",
        "consumption_id.picking_ids.move_ids.quantity",
        "product_id",
    )
    def _compute_qty_done(self):
        for line in self:
            done = 0.0
            for picking in line.consumption_id.sudo().picking_ids:
                is_return = bool(picking.return_id)
                for move in picking.move_ids.filtered(
                    lambda m, p=line.product_id: m.state == "done" and m.product_id == p
                ):
                    qty = move.product_uom._compute_quantity(move.quantity, line.product_uom_id)
                    done += -qty if is_return else qty
            line.qty_done = done
