from odoo import api, models


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "az.approval.mixin"]

    def _mda_exempt(self):
        # ผู้ติดต่อ/ที่อยู่ย่อยใต้ partner ไม่เข้า workflow — ยึดสถานะตัวแม่
        # (จุดบล็อกทรานแซคชันเช็คที่ commercial_partner_id อยู่แล้ว)
        self.ensure_one()
        return bool(self.parent_id)

    @api.model
    def _mda_vals_exempt(self, vals):
        return bool(vals.get("parent_id"))
