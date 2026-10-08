# -*- coding: utf-8 -*-
"""ผูกรายการปรับปรุงสต็อก (stock.move is_inventory) กลับมาที่ใบตรวจนับ"""
from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    az_count_id = fields.Many2one(
        "az.stock.count", "ใบตรวจนับ", index=True, ondelete="set null", copy=False
    )


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _get_inventory_move_values(self, qty, location_id, location_dest_id, package_id=False, package_dest_id=False):
        vals = super()._get_inventory_move_values(
            qty, location_id, location_dest_id, package_id=package_id, package_dest_id=package_dest_id
        )
        if self.env.context.get("az_count_id"):
            vals["az_count_id"] = self.env.context["az_count_id"]
        return vals
