# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .tools import exact_unit_price


class AccountMove(models.Model):
    _inherit = "account.move"

    exact_price_digits = fields.Integer(
        string="ทศนิยมราคาต่อหน่วยในเอกสารพิมพ์",
        compute="_compute_exact_price_digits",
        help="4 เมื่อมีบรรทัดใดกำหนดยอดรวมเอง มิฉะนั้น 2 "
             "ใช้ให้ทั้งคอลัมน์ราคาต่อหน่วยในใบพิมพ์มีทศนิยมเท่ากันทุกบรรทัด",
    )

    @api.depends("invoice_line_ids.exact_subtotal")
    def _compute_exact_price_digits(self):
        for move in self:
            move.exact_price_digits = 4 if any(move.invoice_line_ids.mapped("exact_subtotal")) else 2

    def _prepare_product_base_line_for_taxes_computation(self, product_line):
        """ยัดราคาต่อหน่วยความละเอียดเต็มเข้าเครื่องคิดภาษี

        ทุกเส้นทางของ account.move ที่คิดภาษี (ยอดบนจอ, tax_totals, การสร้าง
        รายการบัญชีตอน post) เรียกผ่าน method นี้จุดเดียว
        """
        res = super()._prepare_product_base_line_for_taxes_computation(product_line)
        if not self.is_invoice(include_receipts=True):
            # โหมด JE ธรรมดาใช้ amount_currency เป็นฐาน ไม่ใช่ price_unit x quantity
            return res
        price = exact_unit_price(
            product_line.exact_subtotal, product_line.quantity, product_line.discount
        )
        if price is not None:
            res["price_unit"] = price
        return res
