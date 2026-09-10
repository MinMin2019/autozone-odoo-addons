# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .tools import check_exact_subtotal, exact_unit_price, stale_warning


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    exact_subtotal = fields.Monetary(
        string="ยอดรวมกำหนดเอง",
        currency_field="currency_id",
        help="กรอกยอดรวมของบรรทัดนี้ให้ตรงกับ PO ลูกค้าที่ใช้ราคาต่อหน่วยทศนิยมมากกว่า 2 ตำแหน่ง\n"
             "ระบบจะถอดราคาต่อหน่วยความละเอียดเต็มกลับไปคำนวณให้ ยอดรวมบรรทัดจะออกมาตรงตามที่กรอก\n\n"
             "ปล่อยว่าง = คำนวณแบบปกติ (จำนวน x ราคาต่อหน่วย)",
    )
    exact_price_unit = fields.Float(
        string="ราคา/หน่วย (ละเอียด)",
        digits=(16, 6),
        compute="_compute_exact_price_unit",
        help="ราคาต่อหน่วยที่ใช้คำนวณจริง ถอดจากยอดรวมกำหนดเอง "
             "ถ้าไม่ได้กำหนดยอดเองจะเท่ากับราคาต่อหน่วยปกติ",
    )

    @api.depends("exact_subtotal", "quantity", "discount", "price_unit")
    def _compute_exact_price_unit(self):
        for line in self:
            line.exact_price_unit = exact_unit_price(
                line.exact_subtotal, line.quantity, line.discount
            ) or line.price_unit

    @api.depends("exact_subtotal")
    def _compute_totals(self):
        # ต่อ depends ของ compute เดิม (ดูหมายเหตุใน sale_order_line._compute_amount)
        return super()._compute_totals()

    @api.constrains("exact_subtotal")
    def _check_exact_subtotal(self):
        for line in self:
            if line.display_type != "product":
                continue
            check_exact_subtotal(line, line.quantity, line.tax_ids)

    @api.onchange("quantity", "price_unit", "discount")
    def _onchange_exact_subtotal_stale(self):
        warning = stale_warning(self, self.quantity)
        if warning:
            return {"warning": warning}
