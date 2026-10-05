from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # core ตั้ง 'order' ให้สินค้าประเภทของทุกตัว → สินค้าเก็บสต็อกถูกวางบิลก่อนส่งของจริง
    # (ต้นเหตุบัญชีพักสต็อก 1410002 ค้าง) ที่นี่ให้สินค้าเก็บสต็อกเป็น 'delivery' แทน
    # บริการ/สินค้าไม่เก็บสต็อก ยังเป็นตาม core (บริการไม่มีการส่งของ ถ้าเป็น delivery จะวางบิลไม่ได้)
    # ผู้ใช้ยังแก้เองได้ในแท็บการขาย; ค่าที่เปลี่ยนไม่ย้อนไปกระทบ SO เก่า (core ไม่ trigger)
    @api.depends('type', 'is_storable')
    def _compute_invoice_policy(self):
        super()._compute_invoice_policy()
        self.filtered('is_storable').invoice_policy = 'delivery'
