from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrCandidate(models.Model):
    _inherit = "hr.candidate"

    # Stock hr.candidate has no ID number at all, and it is the one key that
    # cannot belong to a namesake — so give HR somewhere to type it.
    identification_id = fields.Char(string="เลขบัตรประชาชน", tracking=True)

    blacklist_employee_ids = fields.Many2many(
        "hr.employee", string="ตรงกับคนติด Blacklist",
        compute="_compute_blacklist", compute_sudo=True)
    is_blacklisted = fields.Boolean(
        string="ติด Blacklist", compute="_compute_blacklist", search="_search_is_blacklisted",
        compute_sudo=True)
    blacklist_note = fields.Text(compute="_compute_blacklist", compute_sudo=True)

    # Not stored on purpose: a person can be blacklisted after they applied,
    # and a stored flag on the candidate would never hear about it.
    @api.depends("partner_name", "identification_id", "partner_phone", "email_from")
    def _compute_blacklist(self):
        matcher = self.env["autozone.blacklist.matcher"]
        for candidate in self:
            hits = matcher._find(
                name=candidate.partner_name, id_card=candidate.identification_id,
                phones=(candidate.partner_phone,), email=candidate.email_from)
            candidate.blacklist_employee_ids = hits
            candidate.is_blacklisted = bool(hits)
            candidate.blacklist_note = matcher._describe(hits) if hits else False

    def _search_is_blacklisted(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise UserError(_("ค้นหาได้แค่ ติด / ไม่ติด Blacklist"))
        candidates = self.with_context(active_test=False).search([])
        ids = candidates.filtered("is_blacklisted").ids
        positive = (operator == "=") == value
        return [("id", "in" if positive else "not in", ids)]

    def _check_blacklist(self):
        if self.env["autozone.blacklist.matcher"]._is_override_allowed():
            return
        bad = self.filtered("is_blacklisted")
        if bad:
            raise UserError(_(
                "ผู้สมัครคนนี้ตรงกับคนติด Blacklist ห้ามรับกลับเข้าทำงาน:\n%(who)s\n\n"
                "ถ้าเป็นคนละคนกัน (เช่นชื่อซ้ำ) ให้ HR Manager เป็นผู้ดำเนินการต่อ",
                who=bad[0].blacklist_note))

    def create_employee_from_candidate(self):
        self._check_blacklist()
        return super().create_employee_from_candidate()


class HrApplicant(models.Model):
    _inherit = "hr.applicant"

    is_blacklisted = fields.Boolean(
        related="candidate_id.is_blacklisted", string="ติด Blacklist")
    blacklist_note = fields.Text(related="candidate_id.blacklist_note")
    identification_id = fields.Char(related="candidate_id.identification_id", readonly=False)

    def write(self, vals):
        # Refusing goes through active / refuse_reason_id, not stage_id, so it
        # stays possible; any move along the pipeline does not.
        if "stage_id" in vals:
            self.candidate_id._check_blacklist()
        return super().write(vals)
