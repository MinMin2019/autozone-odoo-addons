# -*- coding: utf-8 -*-
"""ใบโอนสินค้าไปสาขา (H.O. -> สาขา) ครอบ Flow B

ข้างหลังยังเป็นใบ TOUT (H.O./Stock -> คลังพัก) + TIN (คลังพัก -> <สาขา>/Stock) ที่ Odoo
สร้างจาก route "<สาขา>: Supply Product from H.O." เหมือนเดิม — โมดูลนี้แค่:
  * ให้ส่วนกลางกรอกสาขา + สินค้าหลายบรรทัด แล้วกดยืนยันครั้งเดียว (route ถูกล็อกในโค้ด)
  * ปุ่ม "ส่งของ" (validate TOUT) / "รับของ" (validate TIN) บนใบเดียวกัน
  * สถานะไล่ตามใบจริง: ร่าง -> รอส่ง -> ส่งแล้ว รอสาขารับ -> รับบางส่วน -> รับครบ
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

TOUT = "TOUT"
TIN = "TIN"


class BranchTransfer(models.Model):
    _name = "az.branch.transfer"
    _description = "ใบโอนสินค้าไปสาขา"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char("เลขที่", default="/", readonly=True, copy=False)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, readonly=True
    )
    source_warehouse_id = fields.Many2one(
        "stock.warehouse", "ต้นทาง (ส่วนกลาง)", required=True,
        default=lambda self: self._default_source_warehouse(),
        readonly=True, tracking=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse", "สาขาปลายทาง", required=True, tracking=True,
        domain="[('id', '!=', source_warehouse_id), ('resupply_wh_ids', 'in', [source_warehouse_id])]",
        help="เลือกได้เฉพาะสาขาที่ตั้ง 'จัดหาสินค้าจากส่วนกลาง' ไว้แล้ว",
    )
    date = fields.Date("วันที่", default=fields.Date.context_today, required=True, tracking=True)
    note = fields.Text("หมายเหตุ")
    user_id = fields.Many2one(
        "res.users", "ผู้สร้าง", default=lambda self: self.env.user, readonly=True
    )
    line_ids = fields.One2many("az.branch.transfer.line", "transfer_id", "รายการสินค้า", copy=True)
    group_id = fields.Many2one("procurement.group", "Procurement Group", readonly=True, copy=False)
    picking_ids = fields.One2many("stock.picking", "az_transfer_id", "ใบโอน (TOUT/TIN)", copy=False)
    picking_count = fields.Integer(compute="_compute_pickings")
    tout_picking_id = fields.Many2one("stock.picking", "ใบส่ง (TOUT)", compute="_compute_pickings")
    tin_picking_ids = fields.Many2many("stock.picking", compute="_compute_pickings")
    state = fields.Selection(
        [
            ("draft", "ร่าง"),
            ("confirmed", "รอส่วนกลางส่ง"),
            ("sent", "ส่งแล้ว รอสาขารับ"),
            ("partial", "รับบางส่วน"),
            ("done", "รับครบ"),
            ("cancel", "ยกเลิก"),
        ],
        "สถานะ", default="draft", compute="_compute_state", store=True, tracking=True, copy=False,
    )
    cancelled = fields.Boolean(copy=False)
    qty_total = fields.Float("จำนวนรวม", compute="_compute_totals", digits="Product Unit of Measure")
    qty_sent_total = fields.Float("ส่งแล้วรวม", compute="_compute_totals", digits="Product Unit of Measure")
    qty_received_total = fields.Float("รับแล้วรวม", compute="_compute_totals", digits="Product Unit of Measure")
    can_send = fields.Boolean(compute="_compute_permissions")
    can_receive = fields.Boolean(compute="_compute_permissions")

    # ------------------------------------------------------------------
    # defaults / helpers
    # ------------------------------------------------------------------
    @api.model
    def _default_source_warehouse(self):
        ptype = self.env["stock.picking.type"].sudo().search(
            [("sequence_code", "=", TOUT), ("company_id", "=", self.env.company.id)], limit=1
        )
        return ptype.warehouse_id

    def _get_resupply_route(self):
        self.ensure_one()
        route = self.env["stock.route"].sudo().search(
            [
                ("supplied_wh_id", "=", self.warehouse_id.id),
                ("supplier_wh_id", "=", self.source_warehouse_id.id),
                ("active", "=", True),
            ],
            limit=1,
        )
        if not route:
            raise UserError(
                _("สาขา %s ยังไม่ได้ตั้งเส้นทาง 'จัดหาสินค้าจาก %s' (Resupply From) "
                  "กรุณาตั้งค่าที่คลังสินค้าก่อน")
                % (self.warehouse_id.name, self.source_warehouse_id.name)
            )
        return route

    def _user_can_use_warehouse(self, warehouse):
        """ผู้ใช้คนนี้ทำงานแทนคลังนี้ได้ไหม
        มี custom_warehouse_scope -> ใช้ allowed_warehouse_ids; ไม่มี -> ใช้ Default Warehouse
        (ไม่ได้ตั้งทั้งคู่ = ทำได้ทุกคลัง)"""
        user = self.env.user
        if "allowed_warehouse_ids" in user._fields:
            if user.warehouse_unrestricted or not user.allowed_warehouse_ids:
                return True
            return warehouse in user.allowed_warehouse_ids
        default_wh = user.with_company(self.company_id).property_warehouse_id
        return not default_wh or default_wh == warehouse

    # ------------------------------------------------------------------
    # computes (อ่านใบจริงด้วย sudo — สาขาไม่มีสิทธิ์เห็นใบ TOUT ของส่วนกลาง)
    # ------------------------------------------------------------------
    def _real_pickings(self):
        """ใบ TOUT/TIN ของใบโอนนี้ ไม่รวมใบคืน (return)"""
        return self.sudo().picking_ids.filtered(lambda p: not p.return_id)

    @api.depends("picking_ids", "picking_ids.state")
    def _compute_pickings(self):
        for rec in self:
            pickings = rec._real_pickings()
            rec.picking_count = len(rec.sudo().picking_ids)
            rec.tout_picking_id = pickings.filtered(
                lambda p: p.picking_type_id.sequence_code == TOUT
            )[:1]
            rec.tin_picking_ids = pickings.filtered(
                lambda p: p.picking_type_id.sequence_code == TIN
            )

    @api.depends("picking_ids", "picking_ids.state", "cancelled")
    def _compute_state(self):
        for rec in self:
            if rec.cancelled:
                rec.state = "cancel"
                continue
            pickings = rec._real_pickings()
            if not pickings:
                rec.state = "draft"
                continue
            live = pickings.filtered(lambda p: p.state != "cancel")
            if not live:
                rec.state = "cancel"
                continue
            touts = live.filtered(lambda p: p.picking_type_id.sequence_code == TOUT)
            tins = live.filtered(lambda p: p.picking_type_id.sequence_code == TIN)
            tout_done_any = any(p.state == "done" for p in touts)
            tout_done_all = all(p.state == "done" for p in touts)
            tin_done_any = any(p.state == "done" for p in tins)
            tin_done_all = bool(tins) and all(p.state == "done" for p in tins)
            if not tout_done_any:
                rec.state = "confirmed"
            elif tout_done_all and tin_done_all:
                rec.state = "done"
            elif tin_done_any:
                rec.state = "partial"
            else:
                rec.state = "sent"

    @api.depends("line_ids.product_uom_qty", "line_ids.qty_sent", "line_ids.qty_received")
    def _compute_totals(self):
        for rec in self:
            rec.qty_total = sum(rec.line_ids.mapped("product_uom_qty"))
            rec.qty_sent_total = sum(rec.line_ids.mapped("qty_sent"))
            rec.qty_received_total = sum(rec.line_ids.mapped("qty_received"))

    @api.depends("state", "source_warehouse_id", "warehouse_id")
    @api.depends_context("uid")
    def _compute_permissions(self):
        for rec in self:
            rec.can_send = rec.state == "confirmed" and rec._user_can_use_warehouse(
                rec.source_warehouse_id
            )
            rec.can_receive = rec.state in ("sent", "partial") and rec._user_can_use_warehouse(
                rec.warehouse_id
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("az.branch.transfer") or "/"
        return super().create(vals_list)

    def write(self, vals):
        locked = {"warehouse_id", "source_warehouse_id", "line_ids"}
        if locked & set(vals) and any(r.state != "draft" for r in self):
            raise UserError(_("ใบโอนที่ยืนยันแล้วแก้สาขา/รายการสินค้าไม่ได้ ให้ยกเลิกแล้วสร้างใหม่"))
        return super().write(vals)

    def unlink(self):
        if any(r.state not in ("draft", "cancel") for r in self):
            raise UserError(_("ลบได้เฉพาะใบโอนสถานะร่างหรือยกเลิก"))
        return super().unlink()

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def action_confirm(self):
        """สร้าง TOUT + TIN คู่กันผ่าน route ของสาขา (procurement)"""
        Procurement = self.env["procurement.group"].Procurement
        for rec in self:
            if rec.state != "draft":
                continue
            if not rec._user_can_use_warehouse(rec.source_warehouse_id):
                raise UserError(_("เฉพาะผู้ใช้ของ %s (ส่วนกลาง) เท่านั้นที่ยืนยันใบโอนได้")
                                % rec.source_warehouse_id.name)
            lines = rec.line_ids.filtered(lambda l: l.product_uom_qty > 0)
            if not lines:
                raise UserError(_("กรุณาใส่รายการสินค้าอย่างน้อย 1 บรรทัด"))
            dup = lines.mapped("product_id")
            if len(dup) != len(lines):
                raise UserError(_("มีสินค้าซ้ำกันในใบเดียว กรุณารวมเป็นบรรทัดเดียว"))
            route = rec._get_resupply_route()
            group = self.env["procurement.group"].create(
                {"name": rec.name, "move_type": "direct", "az_transfer_id": rec.id}
            )
            rec.group_id = group
            date_planned = fields.Datetime.to_datetime(rec.date)
            procs = []
            for line in lines:
                procs.append(
                    Procurement(
                        line.product_id,
                        line.product_uom_qty,
                        line.product_uom_id,
                        rec.warehouse_id.lot_stock_id,
                        line.product_id.display_name,
                        rec.name,
                        rec.company_id,
                        {
                            "warehouse_id": rec.warehouse_id,
                            "route_ids": route,
                            "group_id": group,
                            "date_planned": date_planned,
                            "company_id": rec.company_id,
                        },
                    )
                )
            self.env["procurement.group"].with_context(az_branch_transfer=True).run(procs)
            pickings = self.env["stock.picking"].sudo().search([("group_id", "=", group.id)])
            if not pickings:
                raise UserError(_("Odoo ไม่ได้สร้างใบโอน — ตรวจสอบเส้นทาง (route) ของสาขา"))
            pickings.write({"az_transfer_id": rec.id, "origin": rec.name})
            rec.invalidate_recordset(["picking_ids"])
            rec.message_post(body=_("สร้างใบโอนแล้ว: %s") % ", ".join(pickings.mapped("name")))
        return True

    def action_send(self):
        """ส่วนกลางกดส่งของ = validate ใบ TOUT (ถ้าของไม่ครบ Odoo จะถาม backorder)"""
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(_("ใบนี้ส่งไปแล้ว หรือยังไม่ได้ยืนยัน"))
        if not self._user_can_use_warehouse(self.source_warehouse_id):
            raise UserError(_("เฉพาะผู้ใช้ของ %s เท่านั้นที่ส่งของได้") % self.source_warehouse_id.name)
        touts = self._real_pickings().filtered(
            lambda p: p.picking_type_id.sequence_code == TOUT and p.state not in ("done", "cancel")
        )
        tout = self.env["stock.picking"].browse(touts.ids)  # กลับมาใช้สิทธิ์ผู้ใช้จริง
        tout.action_assign()
        if all(p.state != "assigned" for p in tout):
            raise UserError(
                _("ของที่ %s ไม่พอจ่ายแม้แต่รายการเดียว (ดูคอลัมน์ 'คงเหลือต้นทาง') "
                  "กรุณารับสินค้าเข้าคลังก่อน หรือยกเลิกใบนี้แล้วสร้างใหม่ตามจำนวนที่มี")
                % self.source_warehouse_id.name
            )
        res = tout.with_context(az_branch_transfer=True).button_validate()
        if isinstance(res, dict):
            return res
        return True

    def action_receive(self):
        """สาขากดรับของทั้งหมดตามที่ส่งมา = validate ใบ TIN ที่ Ready"""
        self.ensure_one()
        if self.state not in ("sent", "partial"):
            raise UserError(_("ต้องรอส่วนกลางส่งของก่อน ถึงจะกดรับได้"))
        if not self._user_can_use_warehouse(self.warehouse_id):
            raise UserError(_("เฉพาะผู้ใช้ของสาขา %s เท่านั้นที่รับของได้") % self.warehouse_id.name)
        tins = self._real_pickings().filtered(
            lambda p: p.picking_type_id.sequence_code == TIN and p.state not in ("done", "cancel")
        )
        tin = self.env["stock.picking"].browse(tins.ids)
        tin.action_assign()
        ready = tin.filtered(lambda p: p.state == "assigned")
        if not ready:
            raise UserError(_("ยังไม่มีของในคลังพักให้รับ — ส่วนกลางยังส่งไม่ครบ"))
        res = ready.with_context(az_branch_transfer=True).button_validate()
        if isinstance(res, dict):
            return res
        return True

    def action_open_receipt(self):
        """เปิดใบ TIN ให้แก้จำนวนรับจริง (รับบางส่วน)"""
        self.ensure_one()
        tins = self._real_pickings().filtered(
            lambda p: p.picking_type_id.sequence_code == TIN and p.state not in ("done", "cancel")
        )
        if not tins:
            raise UserError(_("ไม่มีใบรับที่ค้างอยู่"))
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": tins[0].id,
            "target": "current",
        }

    def action_view_pickings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("ใบโอนของ %s") % self.name,
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("az_transfer_id", "=", self.id)],
            "context": {"create": False},
        }

    def action_cancel(self):
        for rec in self:
            if rec.state in ("sent", "partial", "done"):
                raise UserError(
                    _("ส่วนกลางส่งของออกไปแล้ว ยกเลิกไม่ได้ — ให้กด Return ที่ใบ %s เพื่อรับของกลับ")
                    % (rec.tout_picking_id.name or "TOUT")
                )
            if rec.state == "cancel":
                continue
            pickings = rec._real_pickings().filtered(lambda p: p.state not in ("done", "cancel"))
            pickings.with_context(az_branch_transfer=True).action_cancel()
            rec.write({"cancelled": True})
        return True

    def action_draft(self):
        for rec in self:
            if rec.state != "cancel":
                raise UserError(_("กลับเป็นร่างได้เฉพาะใบที่ยกเลิกแล้ว"))
            rec.sudo().picking_ids.write({"az_transfer_id": False})
            rec.write({"group_id": False, "cancelled": False})
        return True

    def action_print(self):
        self.ensure_one()
        return self.env.ref("custom_branch_transfer.action_report_az_branch_transfer").report_action(self)


class BranchTransferLine(models.Model):
    _name = "az.branch.transfer.line"
    _description = "รายการใบโอนสินค้าไปสาขา"
    _order = "transfer_id, sequence, id"

    transfer_id = fields.Many2one("az.branch.transfer", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        "product.product", "สินค้า", required=True,
        domain="[('is_storable', '=', True)]",
    )
    product_uom_id = fields.Many2one("uom.uom", "หน่วย", related="product_id.uom_id", readonly=True)
    product_uom_qty = fields.Float("จำนวนที่ส่ง", digits="Product Unit of Measure", required=True, default=1.0)
    qty_available_src = fields.Float(
        "คงเหลือต้นทาง", compute="_compute_qty_available_src", digits="Product Unit of Measure"
    )
    qty_sent = fields.Float("ส่งแล้ว", compute="_compute_qty_done", digits="Product Unit of Measure")
    qty_received = fields.Float("สาขารับแล้ว", compute="_compute_qty_done", digits="Product Unit of Measure")
    state = fields.Selection(related="transfer_id.state")
    company_id = fields.Many2one(related="transfer_id.company_id")

    _sql_constraints = [
        ("qty_positive", "CHECK(product_uom_qty > 0)", "จำนวนต้องมากกว่า 0"),
    ]

    @api.depends("product_id", "transfer_id.source_warehouse_id")
    def _compute_qty_available_src(self):
        for line in self:
            wh = line.transfer_id.source_warehouse_id
            if line.product_id and wh:
                line.qty_available_src = line.product_id.sudo().with_context(
                    warehouse_id=wh.id
                ).qty_available
            else:
                line.qty_available_src = 0.0

    @api.depends("transfer_id.picking_ids.state", "transfer_id.picking_ids.move_ids.quantity", "product_id")
    def _compute_qty_done(self):
        for line in self:
            sent = received = 0.0
            for picking in line.transfer_id.sudo().picking_ids:
                code = picking.picking_type_id.sequence_code
                is_return = bool(picking.return_id)
                for move in picking.move_ids.filtered(
                    lambda m, p=line.product_id: m.state == "done" and m.product_id == p
                ):
                    qty = move.product_uom._compute_quantity(move.quantity, line.product_uom_id)
                    if code == TOUT:
                        sent += -qty if is_return else qty
                    elif code == TIN:
                        received += -qty if is_return else qty
            line.qty_sent = sent
            line.qty_received = received
