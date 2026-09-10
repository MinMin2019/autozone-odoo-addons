# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # รูปสินค้า (related) สำหรับแสดงเป็นคอลัมน์ในตาราง order line ตอนสั่งซื้อ
    product_image = fields.Binary(
        string="Image",
        related="product_id.image_128",
        readonly=True,
    )
