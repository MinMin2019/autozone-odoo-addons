from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

STATES = [
    ("draft", "ร่าง"),
    ("division", "รอผู้จัดการฝ่าย"),
    ("line", "รอสายงาน/กรรมการ"),
    ("hr", "HR รับเรื่อง"),
    ("recruiting", "กำลังสรรหา"),
    ("done", "ปิด"),
    ("rejected", "ไม่อนุมัติ"),
    ("cancel", "ยกเลิก"),
]


class ManpowerRequest(models.Model):
    """ใบขออัตรากำลัง — the first lane of HR's recruitment flow."""

    _name = "hr.manpower.request"
    _description = "ใบขออัตรากำลัง"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="เลขที่", readonly=True, copy=False, default="ใหม่")
    state = fields.Selection(STATES, string="สถานะ", default="draft", required=True,
                             tracking=True, copy=False, group_expand="_expand_states")
    request_type = fields.Selection(
        [("replacement", "อัตราทดแทน"), ("new", "อัตราเพิ่มใหม่")],
        string="ประเภท", required=True, default="replacement", tracking=True,
        help="อัตราทดแทน: ผู้จัดการฝ่ายอนุมัติแล้วส่ง HR\n"
             "อัตราเพิ่มใหม่: ต้องผ่านสายงาน/รองกรรมการ/กรรมการอีกขั้น")
    department_id = fields.Many2one("hr.department", string="แผนก", required=True, tracking=True,
                                    default=lambda self: self.env.user.employee_id.department_id)
    job_id = fields.Many2one(
        "hr.job", string="ตำแหน่ง", required=True, tracking=True,
        domain="[('department_id', '=', department_id)]")
    quantity = fields.Integer(string="จำนวนที่ขอ", default=1, required=True, tracking=True)
    replace_employee_ids = fields.Many2many(
        "hr.employee", string="แทนพนักงาน", context={"active_test": False},
        help="คนที่ออกหรือกำลังจะออก — เฉพาะอัตราทดแทน")
    reason = fields.Text(string="เหตุผลที่ขอ", required=True)
    date_required = fields.Date(string="ต้องการภายใน", tracking=True)
    term_type = fields.Selection(
        [("indefinite", "ไม่มีกำหนดระยะเวลา"), ("fixed", "มีกำหนดระยะเวลา")],
        string="ประเภทสัญญา", default="indefinite", required=True)
    requester_id = fields.Many2one(
        "hr.employee", string="ผู้ขอ", required=True, tracking=True,
        default=lambda self: self.env.user.employee_id,
        help="ผู้ขอที่ยังไม่มี login ให้ HR สร้างใบขอแทนแล้วเลือกชื่อผู้ขอ")
    date_request = fields.Date(string="วันที่ขอ", default=fields.Date.context_today, readonly=True)

    # Headcount plan of the position, for reference only — the department picks
    # the request type itself (user decision 2026-10-19).
    job_approved_headcount = fields.Integer(related="job_id.approved_headcount", string="อัตราที่อนุมัติ")
    job_no_of_employee = fields.Integer(related="job_id.no_of_employee", string="คนปัจจุบัน")
    job_headcount_gap = fields.Integer(related="job_id.headcount_gap", string="ขาด/เกิน")
    job_no_of_recruitment = fields.Integer(related="job_id.no_of_recruitment", string="กำลังรับสมัคร")
    job_level = fields.Selection(related="job_id.job_level", string="Job Level")

    # Approvers, frozen when the request is submitted so a later org-chart
    # change does not move a request that is already waiting on someone.
    division_approver_id = fields.Many2one("res.users", string="ผู้จัดการฝ่าย", readonly=True, copy=False)
    line_approver_id = fields.Many2one("res.users", string="สายงาน/กรรมการ", readonly=True, copy=False)
    division_approved_date = fields.Datetime(string="ผู้จัดการฝ่ายอนุมัติเมื่อ", readonly=True, copy=False)
    line_approved_date = fields.Datetime(string="สายงานอนุมัติเมื่อ", readonly=True, copy=False)
    hr_user_id = fields.Many2one("res.users", string="HR ผู้รับผิดชอบ", tracking=True, copy=False)
    reject_reason = fields.Text(string="เหตุผลที่ไม่อนุมัติ", readonly=True, copy=False)
    current_approver_id = fields.Many2one("res.users", compute="_compute_current_approver",
                                          string="รอใครอยู่", store=True)
    is_my_turn = fields.Boolean(compute="_compute_is_my_turn", search="_search_is_my_turn")

    applicant_ids = fields.One2many("hr.applicant", "manpower_request_id", string="ผู้สมัคร")
    hired_count = fields.Integer(compute="_compute_hired_count", string="จ้างแล้ว", store=True)
    applicant_count = fields.Integer(compute="_compute_hired_count", string="จำนวนผู้สมัคร", store=True)
    acknowledged = fields.Boolean(string="หน่วยงานรับทราบ", readonly=True, copy=False, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    _sql_constraints = [("quantity_positive", "CHECK(quantity > 0)", "จำนวนที่ขอต้องมากกว่า 0")]

    def _expand_states(self, states, domain):
        return [key for key, _label in STATES if key not in ("rejected", "cancel")]

    # ------------------------------------------------------------------ compute
    @api.depends("state", "division_approver_id", "line_approver_id", "hr_user_id")
    def _compute_current_approver(self):
        for request in self:
            request.current_approver_id = {
                "division": request.division_approver_id,
                "line": request.line_approver_id,
                "hr": request.hr_user_id,
            }.get(request.state, self.env["res.users"])

    def _compute_is_my_turn(self):
        for request in self:
            request.is_my_turn = request.current_approver_id == self.env.user

    def _search_is_my_turn(self, operator, value):
        mine = (operator == "=") == bool(value)
        return [("current_approver_id", "=" if mine else "!=", self.env.uid)]

    @api.depends("applicant_ids.date_closed", "applicant_ids.active")
    def _compute_hired_count(self):
        for request in self:
            applicants = request.with_context(active_test=False).applicant_ids
            request.applicant_count = len(applicants.filtered("active"))
            request.hired_count = len(applicants.filtered("date_closed"))

    @api.constrains("department_id", "job_id")
    def _check_job_department(self):
        for request in self:
            if request.job_id.department_id and request.job_id.department_id != request.department_id:
                raise ValidationError(_("ตำแหน่ง %s ไม่ได้อยู่ในแผนก %s",
                                        request.job_id.name, request.department_id.name))

    @api.onchange("department_id")
    def _onchange_department_id(self):
        if self.job_id.department_id != self.department_id:
            self.job_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "ใหม่") == "ใหม่":
                number = self.env["ir.sequence"].next_by_code("hr.manpower.request") or "0"
                year = fields.Date.context_today(self).year + 543
                vals["name"] = "MR-%s-%s" % (year, number)
        return super().create(vals_list)

    # ------------------------------------------------------------------ helpers
    def _is_hr_manager(self):
        return self.env["autozone.manpower.approver"].can_act_for_others()

    def _is_hr(self):
        return self.env.user.has_group("hr_recruitment.group_hr_recruitment_user")

    def _check_turn(self, approver):
        """Only the person the step is waiting on may act; someone holding
        "อนุมัติแทนผู้อื่นได้" may act for them, and that is recorded on the request."""
        self.ensure_one()
        if self.env.user == approver or self.env.su:
            return False
        if self._is_hr_manager():
            return True
        raise UserError(_("ใบขอนี้รอ %s อนุมัติ คุณกดแทนไม่ได้", approver.name))

    def _todo(self, user, summary, note=""):
        if user:
            self.env["autozone.manpower.approver"].notifiable(self).activity_schedule(
                "mail.mail_activity_data_todo", user_id=user.id,
                                   summary=summary, note=note,
                                   date_deadline=fields.Date.context_today(self))

    def _close_todos(self, feedback):
        self.activity_ids.action_feedback(feedback=feedback)

    def _hr_responsible(self):
        # The job's Recruiter, unless it is a technical user — the 2026-10 org
        # load created 203 jobs as the superuser, so their Recruiter is OdooBot.
        user = self.job_id.user_id
        if user and (user == self.env.ref("base.user_root") or not user.employee_ids):
            user = self.env["res.users"]
        if not user:
            user = self.env["autozone.manpower.approver"].hr_people("hr_recruitment.group_hr_recruitment_manager")[:1]
        return user

    def _employee_user(self, employee):
        return self.env["autozone.manpower.approver"]._user_of(employee)

    # ------------------------------------------------------------------ actions
    def action_submit(self):
        Approver = self.env["autozone.manpower.approver"]
        for request in self:
            if request.state not in ("draft", "rejected"):
                continue
            found = Approver.resolve(request.department_id)
            division = Approver.require(found["division_user"], found["division_employee"], "ผู้จัดการฝ่าย")
            line = found["line_user"]
            if request.request_type == "new":
                line = Approver.require(line, found["line_employee"], "สายงาน/กรรมการ")
            request.write({"state": "division", "division_approver_id": division.id,
                           "line_approver_id": line.id, "reject_reason": False,
                           "division_approved_date": False, "line_approved_date": False})
            request._todo(division, _("อนุมัติใบขออัตรากำลัง %s", request.name),
                          _("%s · %s %s อัตรา", request.request_type == "new" and "อัตราเพิ่มใหม่" or "อัตราทดแทน",
                            request.job_id.display_name, request.quantity))
        return True

    def action_approve(self):
        for request in self:
            if request.state == "division":
                on_behalf = request._check_turn(request.division_approver_id)
                request._close_todos(_("อนุมัติ"))
                request.division_approved_date = fields.Datetime.now()
                if on_behalf:
                    request._message_log(body=_("%s อนุมัติแทนผู้จัดการฝ่าย %s",
                                                self.env.user.name, request.division_approver_id.name))
                needs_line = request.request_type == "new"
                if needs_line and request.line_approver_id == request.division_approver_id:
                    # One person holds both posts; asking them twice adds nothing.
                    request.line_approved_date = fields.Datetime.now()
                    needs_line = False
                if needs_line:
                    request.state = "line"
                    request._todo(request.line_approver_id, _("อนุมัติอัตราเพิ่มใหม่ %s", request.name))
                else:
                    request._to_hr()
            elif request.state == "line":
                on_behalf = request._check_turn(request.line_approver_id)
                request._close_todos(_("อนุมัติ"))
                request.line_approved_date = fields.Datetime.now()
                if on_behalf:
                    request._message_log(body=_("%s อนุมัติแทน %s",
                                                self.env.user.name, request.line_approver_id.name))
                request._to_hr()
        return True

    def _to_hr(self):
        self.ensure_one()
        hr = self.hr_user_id or self._hr_responsible()
        self.write({"state": "hr", "hr_user_id": hr.id})
        self._todo(hr, _("รับเรื่องใบขออัตรากำลัง %s", self.name))

    def action_open_reject(self):
        self.ensure_one()
        approver = {"division": self.division_approver_id, "line": self.line_approver_id}.get(self.state)
        if not approver:
            raise UserError(_("ไม่อนุมัติได้เฉพาะใบขอที่รออนุมัติ"))
        self._check_turn(approver)
        return {
            "type": "ir.actions.act_window", "res_model": "hr.manpower.request.reject",
            "view_mode": "form", "target": "new", "name": _("ไม่อนุมัติ"),
            "context": {"default_request_id": self.id},
        }

    def _reject(self, reason):
        self.ensure_one()
        self._close_todos(_("ไม่อนุมัติ: %s", reason))
        self.write({"state": "rejected", "reject_reason": reason})
        self._message_log(body=_("ไม่อนุมัติโดย %s: %s", self.env.user.name, reason))
        requester = self._employee_user(self.requester_id) or self.create_uid
        self._todo(requester, _("ทบทวนใบขอ %s ใหม่", self.name), reason)

    def action_hr_accept(self):
        """HR รับเรื่องดำเนินการ — open the position for recruiting."""
        if not self._is_hr():
            raise UserError(_("เฉพาะฝ่ายบุคคล (Recruitment Officer) รับเรื่องได้"))
        for request in self.filtered(lambda r: r.state == "hr"):
            request._close_todos(_("รับเรื่องแล้ว"))
            job = request.job_id.sudo()
            vals = {"no_of_recruitment": job.no_of_recruitment + request.quantity}
            if "is_published" in job._fields:
                vals["is_published"] = True
            # The approvers interview and approve the hire, so they must see this
            # job's applicants — hr_recruitment's interviewer rule reads this list.
            approvers = request.division_approver_id | request.line_approver_id
            vals["interviewer_ids"] = [(4, user.id) for user in approvers]
            job.write(vals)
            request.state = "recruiting"
        return True

    def _register_hire(self):
        """Called when one of its applicants starts work."""
        for request in self:
            job = request.job_id.sudo()
            if job.no_of_recruitment > 0:
                job.no_of_recruitment -= 1
            if request.hired_count >= request.quantity and request.state == "recruiting":
                request.state = "done"
                if "is_published" in job._fields and not job.no_of_recruitment:
                    job.is_published = False

    def action_acknowledge(self):
        for request in self:
            requester = self._employee_user(request.requester_id)
            if self.env.user != requester and not self._is_hr():
                raise UserError(_("กดรับทราบได้เฉพาะผู้ขอหรือฝ่ายบุคคล"))
            request._close_todos(_("หน่วยงานรับทราบ"))
            request.acknowledged = True
        return True

    def action_reset_draft(self):
        self.filtered(lambda r: r.state in ("rejected", "cancel")).write({"state": "draft"})
        return True

    def action_cancel(self):
        for request in self:
            if request.state == "done":
                raise UserError(_("ใบขอที่ปิดแล้วยกเลิกไม่ได้"))
            if request.state == "recruiting":
                job = request.job_id.sudo()
                remaining = max(request.quantity - request.hired_count, 0)
                job.no_of_recruitment = max(job.no_of_recruitment - remaining, 0)
            request._close_todos(_("ยกเลิก"))
            request.state = "cancel"
        return True
