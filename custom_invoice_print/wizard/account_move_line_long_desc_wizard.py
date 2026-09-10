from odoo import fields, models


class AccountMoveLineLongDescWizard(models.TransientModel):
    _name = "account.move.line.long.desc.wizard"
    _description = "Invoice Line Long Description Wizard"

    move_line_id = fields.Many2one("account.move.line", required=True)
    x_custom_name_long = fields.Text(string="รายละเอียดเต็ม")

    def action_apply(self):
        self.ensure_one()
        self.move_line_id.write({
            "x_custom_name_long": self.x_custom_name_long or "",
        })
        return {"type": "ir.actions.act_window_close"}
