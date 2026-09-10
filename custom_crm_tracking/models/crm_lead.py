from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # ประกาศซ้ำเฉพาะ attribute ที่เพิ่ม — ที่เหลือ merge จาก definition เดิม
    date_deadline = fields.Date(tracking=True)
    priority = fields.Selection(tracking=True)
    # stored compute (readonly=False): การ recompute อัตโนมัติจาก stage/scoring
    # จะขึ้น chatter ด้วย ไม่ใช่เฉพาะที่ user แก้เอง
    probability = fields.Float(tracking=True)
    analytic_account_id = fields.Many2one(tracking=True)
