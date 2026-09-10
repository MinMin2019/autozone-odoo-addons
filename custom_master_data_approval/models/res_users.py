from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model_create_multi
    def create(self, vals_list):
        # partner ที่เกิดจากการสร้าง user เป็นข้อมูลระบบ ไม่ต้องเข้าคิวอนุมัติ
        users = super().create(vals_list)
        users.partner_id.sudo().filtered(
            lambda p: p.approval_state != "approved"
        ).write({"approval_state": "approved"})
        return users
