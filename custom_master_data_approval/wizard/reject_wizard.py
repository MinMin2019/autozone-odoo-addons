from odoo import fields, models
from odoo.exceptions import UserError


class AzMdaRejectWizard(models.TransientModel):
    _name = "az.mda.reject.wizard"
    _description = "ตีกลับข้อมูลหลัก"

    res_model = fields.Char(required=True)
    res_ids = fields.Char(required=True)
    reason = fields.Text(string="เหตุผลที่ตีกลับ", required=True)

    def action_reject(self):
        self.ensure_one()
        records = self.env[self.res_model].browse(
            [int(i) for i in self.res_ids.split(",") if i])
        t = records._mda_type()
        if not t or not t._user_is_approver(self.env.user):
            raise UserError("เฉพาะผู้อนุมัติเท่านั้นที่ตีกลับได้")
        records._mda_do_reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
