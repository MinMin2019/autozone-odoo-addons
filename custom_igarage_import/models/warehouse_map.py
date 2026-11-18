from odoo import fields, models


class IgarageWarehouseMap(models.Model):
    _name = "az.igarage.warehouse.map"
    _description = "จับคู่คลัง iGarage กับคลัง Odoo"
    _order = "warehouse_id, igarage_wh_id"

    igarage_wh_id = fields.Integer("รหัสคลัง iGarage", required=True)
    name = fields.Char("ชื่อคลังใน iGarage")
    warehouse_id = fields.Many2one("stock.warehouse", "คลัง Odoo", required=True, ondelete="cascade")
    is_central = fields.Boolean("คลังกลาง (AZG)", help="คลังส่งของให้สาขา — DO จากคลังนี้ = ใบโอนไปสาขา, DO เข้าคลังนี้ = ใบส่งกลับ")
    is_central_use = fields.Boolean("ส่วนกลางตัดใช้เอง (OTH/RMA)",
                                    help="DO ที่คลังกลางส่งไปคลังนี้ = เบิกใช้ของส่วนกลาง → ดึงเป็นใบเบิกของคลัง Odoo ที่จับคู่ (H.O.) ไม่ใช่ใบโอน")
    use_for_consumption = fields.Boolean("ใช้ดึงยอดเบิก", default=True,
                                         help="ดึงยอดเบิกใช้รายเดือนจากคลัง iGarage นี้ (ATP ใช้ AutoPart แทน ให้ปิดไว้)")
    active = fields.Boolean(default=True)

    _sql_constraints = [("igarage_wh_uniq", "unique(igarage_wh_id)", "รหัสคลัง iGarage นี้ถูกจับคู่แล้ว")]
