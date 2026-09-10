# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    # รูปลายเซ็นสำหรับใช้ในเอกสารจัดซื้อ (PO / RFQ)
    purchase_signature = fields.Binary(
        string="Purchase Signature",
        attachment=True,
        help="รูปลายเซ็นที่จะแสดงในช่อง Purchasing ของใบสั่งซื้อและใบขอราคา",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["purchase_signature"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["purchase_signature"]
