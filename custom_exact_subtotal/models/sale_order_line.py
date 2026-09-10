# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .tools import check_exact_subtotal, exact_unit_price, stale_warning


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Monetary = ปัดตามทศนิยมสกุลเงิน (2) ซึ่งคือยอดที่ผู้ใช้ต้องการพอดีอยู่แล้ว
    exact_subtotal = fields.Monetary(
        string="ยอดรวมกำหนดเอง",
        currency_field="currency_id",
        help="กรอกยอดรวมของบรรทัดนี้ให้ตรงกับ PO ลูกค้าที่ใช้ราคาต่อหน่วยทศนิยมมากกว่า 2 ตำแหน่ง\n"
             "ระบบจะถอดราคาต่อหน่วยความละเอียดเต็มกลับไปคำนวณให้ ยอดรวมบรรทัดจะออกมาตรงตามที่กรอก\n\n"
             "ปล่อยว่าง = คำนวณแบบปกติ (จำนวน x ราคาต่อหน่วย)",
    )
    # digits เป็นตัวเลขตรง ๆ ไม่ใช่ชื่อ decimal.precision จึงไม่ผูกกับค่ากลางของระบบ
    # (odoo/fields.py get_digits: ถ้า _digits ไม่ใช่ str จะคืนค่าที่ประกาศไว้ตรง ๆ)
    exact_price_unit = fields.Float(
        string="ราคา/หน่วย (ละเอียด)",
        digits=(16, 6),
        compute="_compute_exact_price_unit",
        help="ราคาต่อหน่วยที่ใช้คำนวณจริง ถอดจากยอดรวมกำหนดเอง "
             "ถ้าไม่ได้กำหนดยอดเองจะเท่ากับราคาต่อหน่วยปกติ",
    )

    @api.depends("exact_subtotal", "product_uom_qty", "discount", "price_unit")
    def _compute_exact_price_unit(self):
        for line in self:
            line.exact_price_unit = exact_unit_price(
                line.exact_subtotal, line.product_uom_qty, line.discount
            ) or line.price_unit

    @api.depends("exact_subtotal")
    def _compute_amount(self):
        # ต่อ depends ของ compute เดิม: odoo/fields.py get_depends() รวม _depends
        # ของทุก override ตาม MRO ยอดจึงคำนวณใหม่เมื่อแก้ยอดรวมกำหนดเอง
        return super()._compute_amount()

    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        """ยัดราคาต่อหน่วยความละเอียดเต็มเข้าเครื่องคิดภาษี

        account.tax._get_base_line_field_value_from_record ให้ค่าที่ส่งมาทับค่าในเรคอร์ด
        ยอดก่อนภาษีของบรรทัดจึงตกลงที่ exact_subtotal พอดี โดย price_unit ที่เก็บใน DB
        ยังเป็น 2 ตำแหน่งเหมือนเดิม
        """
        res = super()._prepare_base_line_for_taxes_computation(**kwargs)
        price = exact_unit_price(self.exact_subtotal, self.product_uom_qty, self.discount)
        if price is not None:
            res["price_unit"] = price
        return res

    def _prepare_invoice_line(self, **optional_values):
        """ส่งยอดกำหนดเองต่อไปยังใบแจ้งหนี้ โดยเฉลี่ยตามจำนวนที่วางบิลจริง

        วางบิลบางส่วน (เช่น SO 168 ชิ้น วางบิล 84) จะได้ยอดครึ่งหนึ่งที่ปัดแล้ว
        ไม่ใช่ยอดเต็มของ SO
        """
        res = super()._prepare_invoice_line(**optional_values)
        price = exact_unit_price(self.exact_subtotal, self.product_uom_qty, self.discount)
        if price is not None and res.get("quantity"):
            res["exact_subtotal"] = self.currency_id.round(
                price * res["quantity"] * (1.0 - (res.get("discount") or 0.0) / 100.0)
            )
        return res

    @api.constrains("exact_subtotal")
    def _check_exact_subtotal(self):
        for line in self:
            check_exact_subtotal(line, line.product_uom_qty, line.tax_id)

    @api.onchange("product_uom_qty", "price_unit", "discount")
    def _onchange_exact_subtotal_stale(self):
        warning = stale_warning(self, self.product_uom_qty)
        if warning:
            return {"warning": warning}
