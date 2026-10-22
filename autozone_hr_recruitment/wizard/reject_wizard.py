from odoo import fields, models


class ManpowerRequestReject(models.TransientModel):
    _name = "hr.manpower.request.reject"
    _description = "ไม่อนุมัติใบขออัตรากำลัง"

    request_id = fields.Many2one("hr.manpower.request", required=True)
    reason = fields.Text(string="เหตุผล", required=True)

    def action_confirm(self):
        request = self.request_id
        approver = {"division": request.division_approver_id, "line": request.line_approver_id}.get(request.state)
        if approver:
            request._check_turn(approver)
        request._reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
