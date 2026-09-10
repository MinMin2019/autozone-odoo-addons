# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    receipt_picking_ids = fields.Many2many(
        "stock.picking",
        "account_move_receipt_picking_rel",
        "move_id",
        "picking_id",
        string="ใบรับสินค้า",
        copy=False,
        readonly=True,
        help="ใบรับสินค้าที่บิลใบนี้ตั้งหนี้ให้ (สร้างผ่านปุ่ม \"สร้างบิลผู้ขาย\" บนใบรับ)",
    )
    receipt_picking_count = fields.Integer(compute="_compute_receipt_picking_count")

    @api.depends("receipt_picking_ids")
    def _compute_receipt_picking_count(self):
        for move in self:
            move.receipt_picking_count = len(move.receipt_picking_ids)

    def action_view_receipt_pickings(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "name": _("ใบรับสินค้า"),
        }
        if len(self.receipt_picking_ids) == 1:
            action.update({"view_mode": "form", "res_id": self.receipt_picking_ids.id})
        else:
            action.update(
                {
                    "view_mode": "list,form",
                    "domain": [("id", "in", self.receipt_picking_ids.ids)],
                }
            )
        return action
