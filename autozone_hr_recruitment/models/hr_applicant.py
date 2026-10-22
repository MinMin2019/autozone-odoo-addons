from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# FM-HR-05 (Rev.01) แบบประเมินผลการสัมภาษณ์ — ten criteria, each 5 ดีมาก … 1 ปรับปรุง.
CRITERIA = [
    ("az_eval_01", "บุคลิก, ท่วงที กริยามารยาท"),
    ("az_eval_02", "การพูดจาโต้ตอบ ความฉลาด ไหวพริบ"),
    ("az_eval_03", "ทัศนคติทั่วไป, องค์กร ตำแหน่งที่สมัคร"),
    ("az_eval_04", "มนุษยสัมพันธ์"),
    ("az_eval_05", "ความรอบรู้ในตำแหน่งที่สมัคร"),
    ("az_eval_06", "ความเหมาะสมกับตำแหน่ง องค์กร"),
    ("az_eval_07", "ประสบการณ์ ความเชี่ยวชาญ"),
    ("az_eval_08", "ความเหมาะสม การศึกษา"),
    ("az_eval_09", "ลักษณะการเป็นผู้นำ"),
    ("az_eval_10", "ความมุ่งหมายในชีวิตการทำงาน"),
]
SCALE = [("5", "5 ดีมาก"), ("4", "4 ดี"), ("3", "3 พอใช้"), ("2", "2 น้อย"), ("1", "1 ปรับปรุง")]
# เกณฑ์การให้คะแนน, on the average
GRADES = [(4.5, "excellent"), (3.5, "very_good"), (2.5, "good"), (1.5, "fair"), (0.0, "poor")]


class HrApplicant(models.Model):
    _inherit = "hr.applicant"

    manpower_request_id = fields.Many2one(
        "hr.manpower.request", string="ใบขออัตรากำลัง", index=True, tracking=True,
        domain="[('job_id', '=', job_id), ('state', 'in', ('recruiting', 'done'))]")
    az_step = fields.Selection(related="stage_id.az_step", string="ขั้น")
    az_start_date = fields.Date(string="วันเริ่มงาน", tracking=True)

    # --- FM-HR-04 เงินเดือน -----------------------------------------------------
    az_salary_unit = fields.Selection([("month", "ต่อเดือน"), ("day", "ต่อวัน")], string="หน่วยเงินเดือนที่ต้องการ",
                                      default="month")
    az_salary_probation = fields.Float(string="เงินเดือนทดลองงาน", tracking=True,
                                       groups="hr_recruitment.group_hr_recruitment_user")
    az_salary_after_probation = fields.Float(string="เงินเดือนผ่านทดลองงาน", tracking=True,
                                             groups="hr_recruitment.group_hr_recruitment_user")

    # --- FM-HR-05 แบบประเมินผลการสัมภาษณ์ -----------------------------------------
    az_interview_date = fields.Date(string="วันที่สัมภาษณ์")
    az_interviewer_id = fields.Many2one("res.users", string="ผู้สัมภาษณ์")
    az_eval_01 = fields.Selection(SCALE, string=CRITERIA[0][1])
    az_eval_02 = fields.Selection(SCALE, string=CRITERIA[1][1])
    az_eval_03 = fields.Selection(SCALE, string=CRITERIA[2][1])
    az_eval_04 = fields.Selection(SCALE, string=CRITERIA[3][1])
    az_eval_05 = fields.Selection(SCALE, string=CRITERIA[4][1])
    az_eval_06 = fields.Selection(SCALE, string=CRITERIA[5][1])
    az_eval_07 = fields.Selection(SCALE, string=CRITERIA[6][1])
    az_eval_08 = fields.Selection(SCALE, string=CRITERIA[7][1])
    az_eval_09 = fields.Selection(SCALE, string=CRITERIA[8][1])
    az_eval_10 = fields.Selection(SCALE, string=CRITERIA[9][1])
    az_score_total = fields.Integer(string="คะแนนรวม", compute="_compute_eval", store=True)
    az_score_avg = fields.Float(string="คะแนนเฉลี่ย", digits=(3, 2), compute="_compute_eval", store=True)
    az_score_grade = fields.Selection(
        [("excellent", "ดีเยี่ยม"), ("very_good", "ดีมาก (ระดับสำนักงาน)"), ("good", "ดี (ระดับพนักงาน)"),
         ("fair", "พอใช้"), ("poor", "ไม่น่าพอใจ")],
        string="ผลการประเมิน", compute="_compute_eval", store=True)
    az_interview_note = fields.Text(string="ความคิดเห็นเพิ่มเติม")
    az_interviewer_opinion = fields.Selection(
        [("hire", "เห็นควรรับเข้าทำงาน"), ("wait_vacancy", "รออัตราว่าง"), ("unsuitable", "ไม่เหมาะสมกับตำแหน่ง"),
         ("compare", "รอเปรียบเทียบ"), ("other_position", "พิจารณาตำแหน่งอื่น")],
        string="ความคิดเห็นของผู้สัมภาษณ์", tracking=True)
    az_other_position = fields.Char(string="ตำแหน่งอื่นที่เสนอ")
    az_eval_manager_decision = fields.Selection([("approve", "อนุมัติ"), ("reject", "ไม่อนุมัติ")],
                                                string="ผู้จัดการ", readonly=True, tracking=True, copy=False)
    az_eval_manager_id = fields.Many2one("res.users", string="ผู้จัดการผู้อนุมัติผลสัมภาษณ์", readonly=True, copy=False)
    az_eval_manager_date = fields.Date(string="วันที่ผู้จัดการอนุมัติ", readonly=True, copy=False)

    # --- อนุมัติจ้าง ----------------------------------------------------------
    az_hire_state = fields.Selection(
        [("none", "ยังไม่ขอ"), ("pending", "รออนุมัติจ้าง"), ("approved", "อนุมัติจ้างแล้ว"),
         ("rejected", "ไม่อนุมัติจ้าง")],
        string="อนุมัติจ้าง", default="none", tracking=True, copy=False)
    az_hire_approver_id = fields.Many2one("res.users", string="ผู้อนุมัติจ้าง", readonly=True, copy=False)
    az_hire_approved_date = fields.Datetime(string="อนุมัติจ้างเมื่อ", readonly=True, copy=False)
    az_is_my_hire_turn = fields.Boolean(compute="_compute_is_my_hire_turn")

    @api.depends(*[f for f, _label in CRITERIA])
    def _compute_eval(self):
        for applicant in self:
            scores = [int(applicant[f]) for f, _label in CRITERIA if applicant[f]]
            applicant.az_score_total = sum(scores)
            # The form averages over all ten; a half-filled form is not graded.
            if len(scores) == len(CRITERIA):
                avg = sum(scores) / len(CRITERIA)
                applicant.az_score_avg = avg
                applicant.az_score_grade = next(g for floor, g in GRADES if avg >= floor)
            else:
                applicant.az_score_avg = 0.0
                applicant.az_score_grade = False

    def _eval_manager(self):
        """The ผู้จัดการ who signs off FM-HR-05: the request's ฝ่าย approver."""
        self.ensure_one()
        user = self.manpower_request_id.division_approver_id
        if not user:
            found = self.env["autozone.manpower.approver"].resolve(self.department_id or self.job_id.department_id)
            user = found["division_user"]
        return user

    def _eval_decide(self, decision):
        for applicant in self:
            manager = applicant._eval_manager()
            on_behalf = self.env.user != manager and not self.env.su
            if on_behalf and not self.env["autozone.manpower.approver"].can_act_for_others():
                raise UserError(_("ผลสัมภาษณ์นี้ให้ %s อนุมัติ", manager.name or _("ผู้จัดการฝ่าย")))
            if not applicant.az_score_grade:
                raise UserError(_("กรอกคะแนนให้ครบ 10 หัวข้อก่อน"))
            if on_behalf:
                applicant._message_log(body=_("%(me)s อนุมัติผลสัมภาษณ์แทน %(who)s",
                                              me=self.env.user.name, who=manager.name or _("ผู้จัดการฝ่าย")))
            applicant.sudo().write({"az_eval_manager_decision": decision, "az_eval_manager_id": self.env.uid,
                                    "az_eval_manager_date": fields.Date.context_today(self)})
        return True

    def action_az_eval_approve(self):
        return self._eval_decide("approve")

    def action_az_eval_reject(self):
        return self._eval_decide("reject")

    def _compute_is_my_hire_turn(self):
        for applicant in self:
            applicant.az_is_my_hire_turn = (applicant.az_hire_state == "pending"
                                            and applicant.az_hire_approver_id == self.env.user)

    # --- link to the request ------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        applicants = super().create(vals_list)
        for applicant in applicants.filtered(lambda a: not a.manpower_request_id and a.job_id):
            # Applications from the website or keyed in by HR land on the oldest
            # request still recruiting for that job.
            request = self.env["hr.manpower.request"].sudo().search(
                [("job_id", "=", applicant.job_id.id), ("state", "=", "recruiting")], order="id", limit=1)
            if request:
                applicant.sudo().manpower_request_id = request
        return applicants

    # --- the hire-approval gate --------------------------------------------
    def write(self, vals):
        if "stage_id" in vals and not self.env.su:
            target = self.env["hr.recruitment.stage"].browse(vals["stage_id"])
            if target.az_step == "hire_approval":
                for applicant in self:
                    if applicant.az_eval_manager_decision != "approve":
                        raise UserError(_(
                            "%s ยังไม่ผ่านการอนุมัติผลสัมภาษณ์จากผู้จัดการ (FM-HR-05)", applicant.partner_name))
            if target.az_step in ("onboarding", "hired"):
                for applicant in self:
                    if applicant.az_hire_state != "approved":
                        raise UserError(_(
                            "%(who)s ยังไม่ได้รับอนุมัติจ้าง — เลื่อนไปขั้น \"%(stage)s\" ไม่ได้",
                            who=applicant.partner_name, stage=target.name))
            if target.az_step == "hired" and not self.env.context.get("az_starting_work"):
                raise UserError(_("ใช้ปุ่ม \"เริ่มงาน\" เพื่อสร้างพนักงานและสัญญา แทนการลากไปขั้นเริ่มงานแล้ว"))
        res = super().write(vals)
        if "stage_id" in vals:
            self.filtered(lambda a: a.az_step == "hire_approval"
                          and a.az_hire_state in ("none", "rejected"))._request_hire_approval()
        return res

    def _request_hire_approval(self):
        Approver = self.env["autozone.manpower.approver"]
        for applicant in self:
            department = applicant.department_id or applicant.job_id.department_id
            found = Approver.resolve(department)
            user = applicant.manpower_request_id.line_approver_id or found["line_user"]
            user = Approver.require(user, found["line_employee"], "อนุมัติจ้าง (สายงาน/กรรมการ)")
            applicant.sudo().write({"az_hire_state": "pending", "az_hire_approver_id": user.id,
                                    "interviewer_ids": [(4, user.id)]})
            self.env["autozone.manpower.approver"].notifiable(applicant).activity_schedule(
                "mail.mail_activity_data_todo", user_id=user.id,
                                        summary=_("อนุมัติจ้าง %s", applicant.partner_name),
                                        note=_("%(job)s · คะแนนเฉลี่ย %(avg)s (%(grade)s)",
                                               job=applicant.job_id.display_name,
                                               avg="%.2f" % applicant.az_score_avg,
                                               grade=dict(self._fields["az_score_grade"].selection).get(
                                                   applicant.az_score_grade, "-")))

    def _check_hire_turn(self):
        self.ensure_one()
        if self.az_hire_state != "pending":
            raise UserError(_("ผู้สมัครนี้ไม่ได้อยู่ระหว่างรออนุมัติจ้าง"))
        if self.env.user == self.az_hire_approver_id or self.env.su:
            return False
        if self.env["autozone.manpower.approver"].can_act_for_others():
            return True
        raise UserError(_("ผู้สมัครนี้รอ %s อนุมัติจ้าง คุณกดแทนไม่ได้", self.az_hire_approver_id.name))

    def action_az_approve_hire(self):
        onboarding = self.env["hr.recruitment.stage"].search([("az_step", "=", "onboarding")], limit=1)
        for applicant in self:
            on_behalf = applicant._check_hire_turn()
            applicant.activity_ids.action_feedback(feedback=_("อนุมัติจ้าง"))
            applicant.sudo().write({"az_hire_state": "approved", "az_hire_approved_date": fields.Datetime.now()})
            if on_behalf:
                applicant._message_log(body=_("%(me)s อนุมัติจ้างแทน %(who)s",
                                              me=self.env.user.name, who=applicant.az_hire_approver_id.name))
            if onboarding:
                applicant.sudo().stage_id = onboarding
            hr = applicant.user_id or applicant.manpower_request_id.hr_user_id
            if hr:
                self.env["autozone.manpower.approver"].notifiable(applicant).activity_schedule(
                    "mail.mail_activity_data_todo", user_id=hr.id,
                                            summary=_("นัดเริ่มงาน %s", applicant.partner_name))
        return True

    def action_az_reject_hire(self):
        for applicant in self:
            applicant._check_hire_turn()
            applicant.activity_ids.action_feedback(feedback=_("ไม่อนุมัติจ้าง"))
            applicant.sudo().write({"az_hire_state": "rejected"})
            applicant._message_log(body=_("ไม่อนุมัติจ้างโดย %s", self.env.user.name))
        return True

    # --- เริ่มงาน -------------------------------------------------------------
    def action_az_start_work(self):
        """Employee + draft contract in one step, then tell the requesting unit."""
        hired_stage = self.env["hr.recruitment.stage"].search([("az_step", "=", "hired")], limit=1)
        for applicant in self:
            if applicant.az_hire_state != "approved":
                raise UserError(_("ต้องได้รับอนุมัติจ้างก่อน"))
            if not applicant.az_start_date:
                raise UserError(_("ใส่วันเริ่มงานก่อนกดเริ่มงาน"))
            if not applicant.employee_id:
                applicant.create_employee_from_applicant()   # passes the blacklist gate
            employee = applicant.employee_id
            request = applicant.manpower_request_id
            department = applicant.department_id or applicant.job_id.department_id
            vals = applicant.candidate_id._az_employee_vals()
            vals.update({"department_id": department.id, "job_id": applicant.job_id.id,
                         "job_title": applicant.job_id.name})
            employee.sudo().write(vals)
            Contract = self.env["hr.contract"].sudo()
            if not Contract.search_count([("employee_id", "=", employee.id)]):
                Contract.create({
                    "name": _("สัญญาจ้าง - %s", employee.name),
                    "employee_id": employee.id,
                    "department_id": department.id,
                    "job_id": applicant.job_id.id,
                    "date_start": applicant.az_start_date,
                    "wage": applicant.sudo().az_salary_probation or applicant.sudo().salary_proposed or 0.0,
                    "term_type": request.term_type if request else "indefinite",
                    "probation_days": 119,
                    "state": "draft",
                })
            applicant.with_context(az_starting_work=True).sudo().write(
                {"stage_id": hired_stage.id, "date_closed": fields.Datetime.now()})
            if request:
                request = request.sudo()
                request._register_hire()
                requester = self.env["autozone.manpower.approver"]._user_of(request.requester_id) or request.create_uid
                request._todo(requester, _("รับทราบพนักงานใหม่ %s", employee.name),
                              _("เริ่มงาน %s · กดปุ่มหน่วยงานรับทราบในใบขอ", applicant.az_start_date))
        return True
