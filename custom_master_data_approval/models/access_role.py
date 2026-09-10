from odoo import models


class AccessRole(models.Model):
    _inherit = "access.role"

    def action_apply(self):
        # action_apply เขียนทับ implied_ids ของกลุ่ม role ทั้งชุด (6,0,...)
        # ต้องเติมกลุ่มผู้อนุมัติ master data กลับทุกครั้ง ไม่งั้นสิทธิ์อนุมัติ
        # หายเงียบ ๆ หลัง re-apply role
        res = super().action_apply()
        self.env["az.approval.type"].sudo().search([])._sync_role_implied()
        return res
