from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    az_abc_class = fields.Selection(
        [("A", "A"), ("B", "B"), ("C", "C")], string="ชั้น ABC", copy=False, index=True,
        help="ผลวิเคราะห์ ABC ล่าสุดที่บันทึกจากรายงาน ABC Analysis (A = มูลค่าใช้สูงสุด 80% แรก)",
    )
    az_abc_date = fields.Date("วันที่วิเคราะห์ ABC", copy=False)
