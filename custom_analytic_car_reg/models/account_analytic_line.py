from odoo import api, fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    # ทะเบียนรถของใบกำกับ/ใบเสร็จที่เป็นต้นทางของบรรทัดวิเคราะห์นี้
    # ดึงได้ 2 ทาง (ใบกำกับกับใบเสร็จใช้คนละฟิลด์):
    #   - x_car_reg_reference  = ฟิลด์ Car Registration ของ custom_invoice_print (ใบแจ้งหนี้/ใบกำกับ)
    #   - license_plate        = ฟิลด์ ทะเบียนรถ ของ custom_garage_receipt (ใบเสร็จรับเงิน out_receipt)
    # store=True เพื่อให้ค้นหา / เรียง / จัดกลุ่มในหน้า Analytic Items ได้
    x_car_reg_reference = fields.Char(
        string="Car Registration",
        compute="_compute_x_car_reg_reference",
        store=True,
        readonly=True,
        help="ทะเบียนรถ (ดึงจากใบกำกับ/ใบเสร็จต้นทาง)",
    )

    @api.depends(
        "move_line_id.move_id.x_car_reg_reference",
        "move_line_id.move_id.license_plate",
    )
    def _compute_x_car_reg_reference(self):
        for line in self:
            move = line.move_line_id.move_id
            line.x_car_reg_reference = (
                move.x_car_reg_reference or move.license_plate or False
            )
