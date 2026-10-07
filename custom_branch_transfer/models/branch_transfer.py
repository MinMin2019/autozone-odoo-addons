# -*- coding: utf-8 -*-
"""ใบโอนสินค้าระหว่างส่วนกลางกับสาขา ครอบ Flow B — 2 ทิศทาง

* direction = out (โอนไปสาขา, เลข BT): ใบ TOUT (H.O./Stock -> คลังพัก) + TIN (คลังพัก -> <สาขา>/Stock)
  ที่ Odoo สร้างจาก route "<สาขา>: Supply Product from H.O." — ส่วนกลางสร้าง/ส่ง สาขากดรับ
* direction = return (สาขาโอนคืนส่วนกลาง, เลข BR): ใบ ROUT (<สาขา>/Stock -> คลังพัก) + RIN
  (คลังพัก -> H.O./Stock) สร้างตรงจากโค้ด (ไม่มี route ขากลับ) move ผูก move_dest_ids กันเอง
  — สาขาสร้าง/ส่ง ส่วนกลางกดรับ; picking type ROUT/RIN สร้างให้อัตโนมัติครั้งแรกที่ใช้

source_warehouse_id = ส่วนกลางเสมอ, warehouse_id = สาขาเสมอ (ไม่ว่าทิศไหน) — ฝั่งส่ง/ฝั่งรับให้ดู
sender_warehouse_id / receiver_warehouse_id
สถานะไล่ตามใบจริง: ร่าง -> รอส่ง -> ส่งแล้ว รอรับ -> รับบางส่วน -> รับครบ
"""
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

TOUT = "TOUT"
TIN = "TIN"
ROUT = "ROUT"
RIN = "RIN"
# ทิศทาง -> (sequence_code ใบส่ง, sequence_code ใบรับ)
CODES = {"out": (TOUT, TIN), "return": (ROUT, RIN)}
SEQ_CODES = {"out": "az.branch.transfer", "return": "az.branch.transfer.return"}


class BranchTransfer(models.Model):
    _name = "az.branch.transfer"
    _description = "ใบโอนสินค้าส่วนกลาง-สาขา"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char("เลขที่", default="/", readonly=True, copy=False)
    direction = fields.Selection(
        [("out", "โอนไปสาขา"), ("return", "สาขาโอนคืนส่วนกลาง")],
        "ประเภท", required=True, default="out", readonly=True, tracking=True,
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, readonly=True
    )
    source_warehouse_id = fields.Many2one(
        "stock.warehouse", "ส่วนกลาง", required=True,
        default=lambda self: self._default_source_warehouse(),
        readonly=True, tracking=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse", "สาขา", required=True, tracking=True,
        default=lambda self: self._default_branch_warehouse(),
        domain="[('id', '!=', source_warehouse_id), ('resupply_wh_ids', 'in', [source_warehouse_id])]",
        help="เลือกได้เฉพาะสาขาที่ตั้ง 'จัดหาสินค้าจากส่วนกลาง' ไว้แล้ว",
    )
    sender_warehouse_id = fields.Many2one(
        "stock.warehouse", "ฝั่งส่ง", compute="_compute_sides", store=True
    )
    receiver_warehouse_id = fields.Many2one(
        "stock.warehouse", "ฝั่งรับ", compute="_compute_sides", store=True
    )
    date = fields.Date("วันที่", default=fields.Date.context_today, required=True, tracking=True)
    note = fields.Text("หมายเหตุ")
    user_id = fields.Many2one(
        "res.users", "ผู้สร้าง", default=lambda self: self.env.user, readonly=True
    )
    line_ids = fields.One2many("az.branch.transfer.line", "transfer_id", "รายการสินค้า", copy=True)
    group_id = fields.Many2one("procurement.group", "Procurement Group", readonly=True, copy=False)
    picking_ids = fields.One2many("stock.picking", "az_transfer_id", "ใบส่ง/ใบรับ", copy=False)
    picking_count = fields.Integer(compute="_compute_pickings")
    tout_picking_id = fields.Many2one("stock.picking", "ใบส่ง", compute="_compute_pickings")
    tin_picking_ids = fields.Many2many("stock.picking", string="ใบรับ", compute="_compute_pickings")
    state = fields.Selection(
        [
            ("draft", "ร่าง"),
            ("confirmed", "รอส่งของ"),
            ("sent", "ส่งแล้ว รอรับ"),
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

    @api.model
    def _default_branch_warehouse(self):
        """ใบโอนคืน: เติมสาขาของผู้ใช้ให้เลย (Default Warehouse / คลังที่อนุญาตคลังเดียว)"""
        if self.env.context.get("default_direction") != "return":
            return False
        user = self.env.user
        wh = user.property_warehouse_id
        if "allowed_warehouse_ids" in user._fields and len(user.allowed_warehouse_ids) == 1:
            wh = user.allowed_warehouse_ids
        if wh and wh != self._default_source_warehouse():
            return wh
        return False

    def _codes(self):
        """(sequence_code ใบส่ง, sequence_code ใบรับ) ตามทิศทาง"""
        self.ensure_one()
        return CODES[self.direction or "out"]

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

    def _get_return_picking_types(self):
        """picking type ขาโอนคืน: <สาขา>: ส่งคืนส่วนกลาง (ROUT) + H.O.: รับคืนจากสาขา (RIN)
        ยังไม่มี = สร้างให้ (คลังพักเดียวกับขาไป = ปลายทางของ TOUT)"""
        self.ensure_one()
        PickingType = self.env["stock.picking.type"].sudo().with_context(active_test=False)
        tout = PickingType.search(
            [("sequence_code", "=", TOUT), ("warehouse_id", "=", self.source_warehouse_id.id)], limit=1
        )
        transit = tout.default_location_dest_id
        if not transit:
            raise UserError(_("ไม่พบคลังพัก (ปลายทางของใบ %s/TOUT) — ตรวจการตั้งค่า Flow B")
                            % self.source_warehouse_id.code)

        def ensure(warehouse, code, name, kind, src, dest):
            ptype = PickingType.search(
                [("sequence_code", "=", code), ("warehouse_id", "=", warehouse.id)], limit=1
            )
            if ptype:
                if not ptype.active:
                    ptype.active = True
                return ptype
            return PickingType.create({
                "name": name,
                "sequence_code": code,
                "code": kind,
                "warehouse_id": warehouse.id,
                "company_id": warehouse.company_id.id,
                "default_location_src_id": src.id,
                "default_location_dest_id": dest.id,
            })

        out_type = ensure(self.warehouse_id, ROUT, "ส่งคืนส่วนกลาง", "outgoing",
                          self.warehouse_id.lot_stock_id, transit)
        in_type = ensure(self.source_warehouse_id, RIN, "รับคืนจากสาขา", "incoming",
                         transit, self.source_warehouse_id.lot_stock_id)
        return out_type, in_type

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
    # computes (อ่านใบจริงด้วย sudo — อีกฝั่งไม่มีสิทธิ์เห็นใบของคลังตรงข้าม)
    # ------------------------------------------------------------------
    @api.depends("direction", "source_warehouse_id", "warehouse_id")
    def _compute_sides(self):
        for rec in self:
            if rec.direction == "return":
                rec.sender_warehouse_id = rec.warehouse_id
                rec.receiver_warehouse_id = rec.source_warehouse_id
            else:
                rec.sender_warehouse_id = rec.source_warehouse_id
                rec.receiver_warehouse_id = rec.warehouse_id

    def _real_pickings(self):
        """ใบส่ง/ใบรับของใบโอนนี้ ไม่รวมใบคืน (return)"""
        return self.sudo().picking_ids.filtered(lambda p: not p.return_id)

    @api.depends("picking_ids", "picking_ids.state", "direction")
    def _compute_pickings(self):
        for rec in self:
            send_code, recv_code = rec._codes()
            pickings = rec._real_pickings()
            rec.picking_count = len(rec.sudo().picking_ids)
            rec.tout_picking_id = pickings.filtered(
                lambda p: p.picking_type_id.sequence_code == send_code
            )[:1]
            rec.tin_picking_ids = pickings.filtered(
                lambda p: p.picking_type_id.sequence_code == recv_code
            )

    @api.depends("picking_ids", "picking_ids.state", "cancelled", "direction")
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
            send_code, recv_code = rec._codes()
            touts = live.filtered(lambda p: p.picking_type_id.sequence_code == send_code)
            tins = live.filtered(lambda p: p.picking_type_id.sequence_code == recv_code)
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

    @api.depends("state", "sender_warehouse_id", "receiver_warehouse_id")
    @api.depends_context("uid")
    def _compute_permissions(self):
        for rec in self:
            rec.can_send = rec.state == "confirmed" and rec._user_can_use_warehouse(
                rec.sender_warehouse_id
            )
            rec.can_receive = rec.state in ("sent", "partial") and rec._user_can_use_warehouse(
                rec.receiver_warehouse_id
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                seq_code = SEQ_CODES[vals.get("direction") or self.env.context.get("default_direction") or "out"]
                vals["name"] = self.env["ir.sequence"].next_by_code(seq_code) or "/"
        return super().create(vals_list)

    def write(self, vals):
        locked = {"warehouse_id", "source_warehouse_id", "line_ids", "direction"}
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
        """สร้างใบส่ง + ใบรับคู่กัน: ขาไปผ่าน route ของสาขา (procurement), ขาคืนสร้างตรง"""
        for rec in self:
            if rec.state != "draft":
                continue
            if not rec._user_can_use_warehouse(rec.sender_warehouse_id):
                raise UserError(_("เฉพาะผู้ใช้ของ %s (ฝั่งส่ง) เท่านั้นที่ยืนยันใบโอนได้")
                                % rec.sender_warehouse_id.name)
            lines = rec.line_ids.filtered(lambda l: l.product_uom_qty > 0)
            if not lines:
                raise UserError(_("กรุณาใส่รายการสินค้าอย่างน้อย 1 บรรทัด"))
            dup = lines.mapped("product_id")
            if len(dup) != len(lines):
                raise UserError(_("มีสินค้าซ้ำกันในใบเดียว กรุณารวมเป็นบรรทัดเดียว"))
            if rec.direction == "return":
                # สาขาคืนได้เฉพาะของที่มีจริง (ขาไปปล่อยให้ส่วนกลางยืนยันรอของเข้าได้)
                short = lines.filtered(lambda l: l._is_short())
                if short:
                    raise UserError(
                        _("ของที่ %s ไม่พอส่งคืน กรุณาแก้จำนวนหรือลบรายการ:\n%s")
                        % (rec.sender_warehouse_id.name, "\n".join(
                            "- %s: มี %s จะส่ง %s" % (l.product_id.display_name,
                                                     l.qty_available_src, l.product_uom_qty)
                            for l in short))
                    )
            group = self.env["procurement.group"].create(
                {"name": rec.name, "move_type": "direct", "az_transfer_id": rec.id}
            )
            rec.group_id = group
            if rec.direction == "return":
                rec._create_return_pickings(lines, group)
            else:
                rec._run_resupply_procurement(lines, group)
            pickings = self.env["stock.picking"].sudo().search([("group_id", "=", group.id)])
            if not pickings:
                raise UserError(_("Odoo ไม่ได้สร้างใบโอน — ตรวจสอบเส้นทาง (route) ของสาขา"))
            vals = {"az_transfer_id": rec.id, "origin": rec.name}
            backdate = rec._backdate_value()
            if backdate:
                vals["backdate"] = backdate
            pickings.write(vals)
            rec.invalidate_recordset(["picking_ids"])
            rec.message_post(body=_("สร้างใบโอนแล้ว: %s") % ", ".join(pickings.mapped("name")))
        return True

    def _run_resupply_procurement(self, lines, group):
        """ขาไป H.O. -> สาขา: run procurement ผ่าน route ของสาขา ได้ TOUT + TIN"""
        self.ensure_one()
        Procurement = self.env["procurement.group"].Procurement
        route = self._get_resupply_route()
        date_planned = fields.Datetime.to_datetime(self.date)
        procs = []
        for line in lines:
            procs.append(
                Procurement(
                    line.product_id,
                    line.product_uom_qty,
                    line.product_uom_id,
                    self.warehouse_id.lot_stock_id,
                    line.product_id.display_name,
                    self.name,
                    self.company_id,
                    {
                        "warehouse_id": self.warehouse_id,
                        "route_ids": route,
                        "group_id": group,
                        "date_planned": date_planned,
                        "company_id": self.company_id,
                    },
                )
            )
        self.env["procurement.group"].with_context(az_branch_transfer=True).run(procs)

    def _create_return_pickings(self, lines, group):
        """ขาคืน สาขา -> H.O.: สร้าง ROUT (สาขา -> คลังพัก) + RIN (คลังพัก -> H.O.)
        move ใบรับเป็น make_to_order ผูกกับ move ใบส่ง -> รอ (Waiting) จนกว่าสาขาจะส่ง"""
        self.ensure_one()
        out_type, in_type = self._get_return_picking_types()
        transit = out_type.default_location_dest_id
        branch_stock = self.warehouse_id.lot_stock_id
        ho_stock = self.source_warehouse_id.lot_stock_id
        scheduled = fields.Datetime.to_datetime(self.date)
        Picking = self.env["stock.picking"].sudo().with_context(az_branch_transfer=True)
        common = {
            "origin": self.name,
            "group_id": group.id,
            "az_transfer_id": self.id,
            "company_id": self.company_id.id,
            "scheduled_date": scheduled,
            "move_type": "direct",
        }
        out_pick = Picking.create(dict(common, picking_type_id=out_type.id,
                                       location_id=branch_stock.id, location_dest_id=transit.id))
        in_pick = Picking.create(dict(common, picking_type_id=in_type.id,
                                      location_id=transit.id, location_dest_id=ho_stock.id))
        Move = self.env["stock.move"].sudo().with_context(az_branch_transfer=True)
        for line in lines:
            move_common = {
                "name": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.product_uom_qty,
                "product_uom": line.product_uom_id.id,
                "group_id": group.id,
                "origin": self.name,
                "company_id": self.company_id.id,
                "date": scheduled,
            }
            in_move = Move.create(dict(
                move_common, picking_id=in_pick.id, picking_type_id=in_type.id,
                location_id=transit.id, location_dest_id=ho_stock.id,
                warehouse_id=self.source_warehouse_id.id, procure_method="make_to_order",
            ))
            Move.create(dict(
                move_common, picking_id=out_pick.id, picking_type_id=out_type.id,
                location_id=branch_stock.id, location_dest_id=transit.id,
                warehouse_id=self.warehouse_id.id, procure_method="make_to_stock",
                move_dest_ids=[(4, in_move.id)],
            ))
        (out_pick | in_pick).action_confirm()
        out_pick.action_assign()

    def _backdate_value(self):
        """วันที่ใบโอนย้อนหลัง -> backdate (เที่ยงวันตามเขตเวลา) ให้ custom_stock_backdate ประทับวันส่ง/รับ
        คืน False ถ้าเป็นวันนี้ หรือไม่ได้ติดตั้ง custom_stock_backdate"""
        self.ensure_one()
        if "backdate" not in self.env["stock.picking"]._fields:
            return False
        if self.date >= fields.Date.context_today(self):
            return False
        tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz
                           or self.company_id.partner_id.tz or "Asia/Bangkok")
        local_noon = tz.localize(datetime.combine(self.date, time(12, 0)))
        return local_noon.astimezone(pytz.utc).replace(tzinfo=None)

    @api.constrains("date")
    def _check_date_not_future(self):
        for rec in self:
            if rec.date and rec.date > fields.Date.context_today(rec):
                raise UserError(_("วันที่ใบโอนเป็นอนาคตไม่ได้"))

    def action_send(self):
        """ฝั่งส่งกดส่งของ = validate ใบส่ง (TOUT/ROUT) (ถ้าของไม่ครบ Odoo จะถาม backorder)"""
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(_("ใบนี้ส่งไปแล้ว หรือยังไม่ได้ยืนยัน"))
        if not self._user_can_use_warehouse(self.sender_warehouse_id):
            raise UserError(_("เฉพาะผู้ใช้ของ %s เท่านั้นที่ส่งของได้") % self.sender_warehouse_id.name)
        send_code = self._codes()[0]
        touts = self._real_pickings().filtered(
            lambda p: p.picking_type_id.sequence_code == send_code and p.state not in ("done", "cancel")
        )
        tout = self.env["stock.picking"].browse(touts.ids)  # กลับมาใช้สิทธิ์ผู้ใช้จริง
        tout.action_assign()
        if all(p.state != "assigned" for p in tout):
            raise UserError(
                _("ของที่ %s ไม่พอจ่ายแม้แต่รายการเดียว (ดูคอลัมน์ 'คงเหลือต้นทาง') "
                  "กรุณารับสินค้าเข้าคลังก่อน หรือยกเลิกใบนี้แล้วสร้างใหม่ตามจำนวนที่มี")
                % self.sender_warehouse_id.name
            )
        res = tout.with_context(az_branch_transfer=True).button_validate()
        if isinstance(res, dict):
            return res
        return True

    def action_receive(self):
        """ฝั่งรับกดรับของทั้งหมดตามที่ส่งมา = validate ใบรับ (TIN/RIN) ที่ Ready"""
        self.ensure_one()
        if self.state not in ("sent", "partial"):
            raise UserError(_("ต้องรอฝั่งส่งส่งของก่อน ถึงจะกดรับได้"))
        if not self._user_can_use_warehouse(self.receiver_warehouse_id):
            raise UserError(_("เฉพาะผู้ใช้ของ %s เท่านั้นที่รับของได้") % self.receiver_warehouse_id.name)
        tins = self._open_receipts()
        tin = self.env["stock.picking"].browse(tins.ids)
        tin.action_assign()
        ready = tin.filtered(lambda p: p.state == "assigned")
        if not ready:
            raise UserError(_("ยังไม่มีของในคลังพักให้รับ — ฝั่งส่งยังส่งไม่ครบ"))
        res = ready.with_context(az_branch_transfer=True).button_validate()
        if isinstance(res, dict):
            return res
        return True

    def _open_receipts(self):
        recv_code = self._codes()[1]
        return self._real_pickings().filtered(
            lambda p: p.picking_type_id.sequence_code == recv_code and p.state not in ("done", "cancel")
        )

    def action_open_receipt(self):
        """เปิดใบรับให้แก้จำนวนรับจริง (รับบางส่วน)"""
        self.ensure_one()
        tins = self._open_receipts()
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
                    _("%s ส่งของออกไปแล้ว ยกเลิกไม่ได้ — ให้กด Return ที่ใบ %s เพื่อรับของกลับ")
                    % (rec.sender_warehouse_id.name, rec.tout_picking_id.name or rec._codes()[0])
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
            # ใบส่ง/ใบรับคู่เดิมที่ยกเลิกและไม่เคยตัดสต็อก = ขยะ ลบทิ้งเลย (ยืนยันใหม่จะได้คู่ใหม่)
            pickings = rec.sudo().picking_ids
            junk = pickings.filtered(
                lambda p: p.state == "cancel" and not p.move_ids.filtered(lambda m: m.state == "done")
            )
            (pickings - junk).write({"az_transfer_id": False})
            names = junk.mapped("name")
            group = rec.sudo().group_id
            junk.unlink()
            rec.write({"group_id": False, "cancelled": False})
            if group and not self.env["stock.picking"].sudo().search_count([("group_id", "=", group.id)]):
                group.unlink()
            if names:
                rec.message_post(body=_("ลบใบที่ยกเลิกแล้ว: %s") % ", ".join(names))
        return True

    def action_print(self):
        self.ensure_one()
        return self.env.ref("custom_branch_transfer.action_report_az_branch_transfer").report_action(self)


class BranchTransferLine(models.Model):
    _name = "az.branch.transfer.line"
    _description = "รายการใบโอนสินค้าส่วนกลาง-สาขา"
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
    qty_received = fields.Float("รับแล้ว", compute="_compute_qty_done", digits="Product Unit of Measure")
    state = fields.Selection(related="transfer_id.state")
    company_id = fields.Many2one(related="transfer_id.company_id")

    _sql_constraints = [
        ("qty_positive", "CHECK(product_uom_qty > 0)", "จำนวนต้องมากกว่า 0"),
    ]

    @api.depends("product_id", "transfer_id.sender_warehouse_id")
    def _compute_qty_available_src(self):
        for line in self:
            wh = line.transfer_id.sender_warehouse_id
            if line.product_id and wh:
                line.qty_available_src = line.product_id.sudo().with_context(
                    warehouse_id=wh.id
                ).qty_available
            else:
                line.qty_available_src = 0.0

    def _is_short(self):
        self.ensure_one()
        return bool(self.product_id) and float_compare(
            self.product_uom_qty, self.qty_available_src,
            precision_rounding=self.product_uom_id.rounding or 0.01,
        ) > 0

    @api.onchange("product_id", "product_uom_qty")
    def _onchange_warn_short(self):
        """เตือนทันทีตอนเลือกสินค้า/แก้จำนวน ถ้าฝั่งส่งมีของไม่พอ"""
        if self.transfer_id.state not in (False, "draft") or not self._is_short():
            return
        wh = self.transfer_id.sender_warehouse_id
        msg = _("%s มี '%s' คงเหลือ %s แต่จะส่ง %s") % (
            wh.name, self.product_id.display_name, self.qty_available_src, self.product_uom_qty)
        if self.transfer_id.direction == "return":
            msg += _("\nใบโอนคืนจะกดยืนยันไม่ได้จนกว่าจะแก้จำนวน")
        return {"warning": {"title": _("ของไม่พอ"), "message": msg}}

    @api.depends("transfer_id.picking_ids.state", "transfer_id.picking_ids.move_ids.quantity", "product_id")
    def _compute_qty_done(self):
        for line in self:
            sent = received = 0.0
            send_code, recv_code = CODES[line.transfer_id.direction or "out"]
            for picking in line.transfer_id.sudo().picking_ids:
                code = picking.picking_type_id.sequence_code
                is_return = bool(picking.return_id)
                for move in picking.move_ids.filtered(
                    lambda m, p=line.product_id: m.state == "done" and m.product_id == p
                ):
                    qty = move.product_uom._compute_quantity(move.quantity, line.product_uom_id)
                    if code == send_code:
                        sent += -qty if is_return else qty
                    elif code == recv_code:
                        received += -qty if is_return else qty
            line.qty_sent = sent
            line.qty_received = received
