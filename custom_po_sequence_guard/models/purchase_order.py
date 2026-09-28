# -*- coding: utf-8 -*-
"""กันเลข PO ซ้ำ

* create: ถ้าตัวนับออกเลขที่มี PO ใช้อยู่แล้ว ให้ข้ามไปเลขถัดไป (log warning ไว้ + trigger ใน
  az_sequence_audit จะบอกว่าใครทำตัวนับถอย) ผู้ใช้ทำงานต่อได้ไม่ติด error
* constraint: ห้ามบันทึก/แก้ชื่อ PO ให้ซ้ำกับใบอื่น (ใบเก่าที่ซ้ำอยู่ก่อนติดตั้งไม่ถูกตรวจจนกว่าจะแก้ชื่อ)
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _az_name_used(self, name):
        return bool(self.sudo().with_context(active_test=False).search_count([("name", "=", name)], limit=1))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") != "New":
                continue
            # เหมือน core purchase.order.create แต่ข้ามเลขที่ถูกใช้แล้ว
            company_id = vals.get("company_id", self.default_get(["company_id"])["company_id"])
            self_comp = self.with_company(company_id)
            seq_date = None
            if "date_order" in vals:
                seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals["date_order"]))
            name = False
            for _i in range(100):
                name = self_comp.env["ir.sequence"].next_by_code("purchase.order", sequence_date=seq_date)
                if not name or not self._az_name_used(name):
                    break
                _logger.warning("PO sequence gave already-used number %s -> skip to next", name)
            vals["name"] = name or "/"
        return super().create(vals_list)

    @api.constrains("name")
    def _check_az_unique_name(self):
        for order in self:
            if not order.name or order.name in ("New", "/"):
                continue
            dup = self.sudo().with_context(active_test=False).search(
                [("name", "=", order.name), ("id", "!=", order.id)], limit=1)
            if dup:
                raise ValidationError(_("เลข PO %s ซ้ำกับใบที่มีอยู่แล้ว (id %s) กรุณาใช้เลขอื่น") % (order.name, dup.id))
