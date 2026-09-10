from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'  # เป็นการสืบทอด (Inherit) เพื่อเพิ่มฟิลด์ในตารางเดิมของ Odoo

    # ประกาศ 4 ฟิลด์ใหม่เป็นรูปแบบข้อความ (Char)
    custom_payment_method = fields.Selection(
        selection=[
            ('Cash', 'Cash'),
            ('Transfer money', 'Transfer Money'),
        ],
        string='การชำระเงิน',
        default='Transfer money',
    )
    repair_job_no = fields.Char(string='เลขที่งานซ่อม')
    vehicle_brand = fields.Char(string='ยี่ห้อ')
    license_plate = fields.Char(string='ทะเบียนรถ')
