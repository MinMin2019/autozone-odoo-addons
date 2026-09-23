# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    az_consumption_id = fields.Many2one(
        "az.branch.consumption", "ใบเบิกใช้วัสดุ", index=True, copy=False, readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        # ใบเบิกคืน (return ของใบ CONS) ให้ผูกกับใบเบิกใช้วัสดุใบเดิม
        # เพื่อให้ยอด "เบิกแล้ว (สุทธิ)" หักของที่คืนออก
        for vals in vals_list:
            if vals.get("return_id") and not vals.get("az_consumption_id"):
                origin = self.browse(vals["return_id"]).sudo()
                if origin.az_consumption_id:
                    vals["az_consumption_id"] = origin.az_consumption_id.id
        return super().create(vals_list)
