# -*- coding: utf-8 -*-
from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    # รูปสินค้า (related) สำหรับแสดงเป็นคอลัมน์ในแท็บ Operations ของใบโอนย้าย
    product_image = fields.Binary(
        string="Image",
        related="product_id.image_128",
        readonly=True,
    )
