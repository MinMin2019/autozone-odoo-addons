# -*- coding: utf-8 -*-
"""กันพลาด 2 จุดที่ทำให้ Flow B พัง

1. ห้ามสร้างใบ TOUT/TIN เอง (ต้องมาจากใบโอนสินค้าไปสาขา) — ยกเว้น backorder และ return
2. ห้าม Validate ใบ TIN ก่อนที่ใบ TOUT ต้นทางจะ Done (กันคลังพักติดลบจากการกรอกจำนวนเอง)
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

GUARDED = ("TOUT", "TIN")


class ProcurementGroup(models.Model):
    _inherit = "procurement.group"

    az_transfer_id = fields.Many2one("az.branch.transfer", "ใบโอนสินค้าไปสาขา", index=True)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    az_transfer_id = fields.Many2one(
        "az.branch.transfer", "ใบโอนสินค้าไปสาขา", index=True, copy=True, readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("az_branch_transfer"):
            PickingType = self.env["stock.picking.type"].sudo()
            Group = self.env["procurement.group"].sudo()
            for vals in vals_list:
                ptype = PickingType.browse(vals.get("picking_type_id"))
                if not ptype or ptype.sequence_code not in GUARDED:
                    continue
                if vals.get("return_id") or vals.get("backorder_id"):
                    continue
                group = Group.browse(vals.get("group_id")) if vals.get("group_id") else Group
                if group and group.az_transfer_id:
                    continue
                raise UserError(
                    _("ประเภท '%s' สร้างเองไม่ได้ — ให้ใช้เมนู Inventory > โอนสินค้าไปสาขา "
                      "(ระบบจะสร้างใบส่ง/ใบรับคู่กันให้อัตโนมัติ)") % ptype.display_name
                )
        return super().create(vals_list)

    def button_validate(self):
        self._az_check_tin_ready()
        return super().button_validate()

    def _az_check_tin_ready(self):
        """ใบ TIN ต้องมีของในคลังพักจริง (TOUT ต้นทาง Done แล้ว) ถึงจะรับได้"""
        for picking in self:
            if picking.picking_type_id.sequence_code != "TIN" or picking.return_id:
                continue
            for move in picking.move_ids.filtered(lambda m: m.state not in ("done", "cancel")):
                origs = move.sudo().move_orig_ids.filtered(lambda m: m.state != "cancel")
                if origs and any(m.state != "done" for m in origs):
                    raise UserError(
                        _("รับไม่ได้: ส่วนกลางยังไม่ได้ส่ง '%s' (ใบ %s ยังไม่ Validate) "
                          "กรุณารอสถานะใบรับเป็น Ready แล้วค่อยกด")
                        % (move.product_id.display_name,
                           ", ".join(origs.mapped("picking_id.name")))
                    )
                if not origs:
                    # ใบ TIN ที่ไม่มีต้นทาง (สร้างมือสมัยก่อน) — ต้องมีของในคลังพักพอ
                    available = move.product_id.sudo().with_context(
                        location=move.location_id.id
                    ).qty_available
                    if move.product_uom._compute_quantity(
                        move.quantity, move.product_id.uom_id
                    ) > available + 1e-6:
                        raise UserError(
                            _("รับไม่ได้: ในคลังพักมี '%s' แค่ %s แต่จะรับ %s")
                            % (move.product_id.display_name, available, move.quantity)
                        )
