from odoo import _, api, fields, models


class ManpowerRequest(models.Model):
    _inherit = "hr.manpower.request"

    resignation_id = fields.Many2one("hr.resignation", string="จากใบลาออก", readonly=True, copy=False)

    @api.model
    def _az_draft_replacement(self, employee, date_needed, note, resignation=None):
        """A draft อัตราทดแทน for someone who is leaving.

        Only a draft: the department still decides whether to replace the seat,
        so it is handed to the department head to check and submit, never sent
        for approval on its own. One request per leaver — a second departure
        event for the same person (resignation approved, then archived) finds the
        first draft and does nothing.
        """
        employee = employee.sudo()
        department, job = employee.department_id, employee.job_id
        if not department or not job:
            return self.browse()   # acting stand-ins and people outside the structure
        existing = self.sudo().search([("replace_employee_ids", "in", employee.ids), ("state", "!=", "cancel")], limit=1)
        if existing:
            return existing
        requester = department.manager_id or employee.parent_id or employee
        contract = employee.contract_id
        request = self.sudo().create({
            "request_type": "replacement",
            "department_id": department.id,
            "job_id": job.id,
            "quantity": 1,
            "replace_employee_ids": [(6, 0, employee.ids)],
            "date_required": date_needed,
            "term_type": contract.term_type if contract and "term_type" in contract._fields else "indefinite",
            "requester_id": requester.id,
            "reason": note,
            "resignation_id": resignation.id if resignation else False,
        })
        A = self.env["autozone.manpower.approver"]
        user = A._user_of(requester) or request._hr_responsible()
        request._todo(user, _("ตรวจใบขอทดแทน %(no)s (%(who)s ลาออก) แล้วกดส่งอนุมัติ", no=request.name, who=employee.name),
                      _("ไม่ต้องการคนแทน กดยกเลิกใบขอได้"))
        request._message_log(body=_("สร้างร่างอัตโนมัติจากการลาออกของ %s", employee.name))
        return request
