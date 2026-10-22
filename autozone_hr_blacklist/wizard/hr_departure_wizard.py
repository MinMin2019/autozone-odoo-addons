from odoo import fields, models


class HrDepartureWizard(models.TransientModel):
    _inherit = "hr.departure.wizard"

    no_rehire = fields.Boolean(string="ติด Blacklist ห้ามรับกลับ")
    no_rehire_reason = fields.Text(string="เหตุผลที่ติด Blacklist")

    def action_register_departure(self):
        res = super().action_register_departure()
        if self.no_rehire:
            self.employee_id.write({
                "no_rehire": True,
                "no_rehire_reason": self.no_rehire_reason,
            })
        return res
