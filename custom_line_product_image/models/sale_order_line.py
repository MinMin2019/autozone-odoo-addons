# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # รูปสินค้า (related) สำหรับแสดงเป็นคอลัมน์ในแท็บรายการคำสั่งซื้อ
    product_image = fields.Binary(
        string="Image",
        related="product_id.image_128",
        readonly=True,
    )
