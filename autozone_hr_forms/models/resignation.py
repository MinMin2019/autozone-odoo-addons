from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

RETURN = [("returned", "คืนแล้ว"), ("not_returned", "ยังไม่ได้คืน"), ("never", "ยังไม่เคยได้")]
STEPS = [("manager", "ผู้จัดการ"), ("gm", "GM"), ("hr", "แผนกบุคคล"), ("md", "กรรมการผู้จัดการ")]


class HrResignation(models.Model):
    """ใบลาออก FM-HR-27 (Rev.00) and its บันทึกแบบสำรวจพนักงานลาออก."""

    _name = "hr.resignation"
    _description = "ใบลาออก"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="เลขที่", readonly=True, copy=False, default="ใหม่")
    state = fields.Selection(
        [("draft", "ร่าง"), ("manager", "รอผู้จัดการ"), ("gm", "รอ GM"), ("hr", "รอแผนกบุคคล"),
         ("md", "รอกรรมการผู้จัดการ"), ("approved", "อนุมัติแล้ว"), ("done", "ลงลาออกแล้ว"),
         ("rejected", "ไม่อนุมัติ"), ("cancel", "ยกเลิก")],
        default="draft", tracking=True, required=True, copy=False)
    date_written = fields.Date(string="วันที่เขียนใบลาออก", default=fields.Date.context_today, required=True)
    employee_id = fields.Many2one("hr.employee", string="พนักงาน", required=True, tracking=True,
                                  default=lambda self: self.env.user.employee_id)
    registration_number = fields.Char(related="employee_id.registration_number", string="รหัสพนักงาน")
    job_title = fields.Char(related="employee_id.job_title", string="ตำแหน่ง")
    department_id = fields.Many2one(related="employee_id.department_id", string="แผนก", store=True)
    branch = fields.Char(string="สาขา", compute="_compute_branch", store=True)
    date_effective = fields.Date(string="ลาออกตั้งแต่วันที่", required=True, tracking=True)
    date_last_day = fields.Date(string="ทำงานวันสุดท้ายวันที่", required=True, tracking=True)
    reason = fields.Text(string="เหตุผลที่ขอลาออก", required=True)

    # Approvers, resolved from the org chart when the form is submitted.
    manager_user_id = fields.Many2one("res.users", string="ผู้จัดการ", readonly=True, copy=False)
    gm_user_id = fields.Many2one("res.users", string="GM", readonly=True, copy=False)
    md_user_id = fields.Many2one("res.users", string="กรรมการผู้จัดการ", readonly=True, copy=False)
    manager_date = fields.Date(string="ผู้จัดการ ลงวันที่", readonly=True, copy=False)
    gm_date = fields.Date(string="GM ลงวันที่", readonly=True, copy=False)
    hr_user_id = fields.Many2one("res.users", string="แผนกบุคคล", readonly=True, copy=False)
    hr_date = fields.Date(string="แผนกบุคคล ลงวันที่", readonly=True, copy=False)
    md_date = fields.Date(string="กรรมการผู้จัดการ ลงวันที่", readonly=True, copy=False)
    reject_reason = fields.Text(string="เหตุผลที่ไม่อนุมัติ", readonly=True, copy=False)
    is_my_turn = fields.Boolean(compute="_compute_is_my_turn")
    manpower_request_id = fields.Many2one("hr.manpower.request", string="ใบขอทดแทน", readonly=True, copy=False)

    # --- บันทึกแบบสำรวจพนักงานลาออก: ส่วน HR -------------------------------------
    uniform_shirt = fields.Selection(RETURN, string="ชุดฟอร์ม เสื้อ")
    uniform_shirt_qty = fields.Integer(string="จำนวนเสื้อ (ตัว)")
    uniform_pants = fields.Selection(RETURN, string="ชุดฟอร์ม กางเกง")
    uniform_pants_qty = fields.Integer(string="จำนวนกางเกง (ตัว)")
    probation_tshirt = fields.Selection(RETURN, string="เสื้อยืดทดลองงาน")
    probation_tshirt_qty = fields.Integer(string="จำนวนเสื้อยืด (ตัว)")
    safety_shoes = fields.Selection(RETURN, string="รองเท้า Safety")
    safety_shoes_qty = fields.Integer(string="จำนวนรองเท้า (คู่)")
    igarage_user = fields.Selection([("deleted", "ลบแล้ว"), ("not_yet", "ยังไม่ได้")], string="User I-garage")
    hr_checker_id = fields.Many2one("res.users", string="ผู้ตรวจสอบ (HR)")
    hr_check_date = fields.Date(string="วันที่ตรวจสอบ (HR)")
    # --- ส่วนบัญชี/ทรัพย์สิน -------------------------------------------------------
    tools = fields.Selection(RETURN, string="อุปกรณ์ช่าง/ตู้เครื่องมือ")
    tools_qty = fields.Integer(string="จำนวนอุปกรณ์ (ชิ้น)")
    other_expense = fields.Selection([("none", "ไม่มีค่าใช้จ่าย"), ("has", "มีค่าใช้จ่าย")], string="ค่าใช้จ่ายอื่น ๆ เพิ่มเติม")
    other_expense_detail = fields.Text(string="รายละเอียดค่าใช้จ่าย")
    acc_checker_id = fields.Many2one("res.users", string="ผู้ตรวจสอบ (บัญชี/ทรัพย์สิน)")
    acc_check_date = fields.Date(string="วันที่ตรวจสอบ (บัญชี)")
    checklist_complete = fields.Boolean(string="สำรวจครบ", compute="_compute_checklist_complete")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    @api.depends("department_id")
    def _compute_branch(self):
        for rec in self:
            dept = rec.department_id
            rec.branch = dept.name if dept and (dept.name or "").startswith("สาขา") else False

    @api.depends("uniform_shirt", "uniform_pants", "probation_tshirt", "safety_shoes", "igarage_user",
                 "tools", "other_expense", "hr_checker_id", "acc_checker_id")
    def _compute_checklist_complete(self):
        for rec in self:
            rec.checklist_complete = all([rec.uniform_shirt, rec.uniform_pants, rec.probation_tshirt, rec.safety_shoes,
                                          rec.igarage_user, rec.tools, rec.other_expense,
                                          rec.hr_checker_id, rec.acc_checker_id])

    def _compute_is_my_turn(self):
        for rec in self:
            rec.is_my_turn = rec._approver() == self.env.user if rec.state in ("manager", "gm", "md") else (
                rec.state == "hr" and self.env.user.has_group("hr.group_hr_user"))

    @api.constrains("date_effective", "date_last_day", "date_written")
    def _check_dates(self):
        for rec in self:
            if rec.date_last_day and rec.date_effective and rec.date_last_day > rec.date_effective:
                raise ValidationError(_("วันทำงานวันสุดท้ายต้องไม่หลังวันที่ลาออก"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "ใหม่") == "ใหม่":
                number = self.env["ir.sequence"].next_by_code("hr.resignation") or "0"
                vals["name"] = "RS-%s-%s" % (fields.Date.context_today(self).year + 543, number)
        return super().create(vals_list)

    # ------------------------------------------------------------------ flow
    def _approver(self):
        return {"manager": self.manager_user_id, "gm": self.gm_user_id, "md": self.md_user_id}.get(
            self.state, self.env["res.users"])

    def _todo(self, user, summary):
        if user:
            self.env["autozone.manpower.approver"].notifiable(self).activity_schedule(
                "mail.mail_activity_data_todo", user_id=user.id, summary=summary,
                                   date_deadline=fields.Date.context_today(self))

    def _hr_users(self):
        return self.env["autozone.manpower.approver"].hr_people("hr.group_hr_manager")

    def _goto(self, step):
        """Move to `step`, skipping steps whose approver already signed an earlier one."""
        order = [s for s, _label in STEPS]
        signed = {self.env.user}
        for current in order[order.index(step):]:
            user = {"manager": self.manager_user_id, "gm": self.gm_user_id, "md": self.md_user_id}.get(current)
            # One person often holds two of these posts (a ฝ่าย with no manager
            # goes to its สายงาน head, who is also GM); they sign once.
            if current != "hr" and user and user in signed:
                self.write({current + "_date": fields.Date.context_today(self)})
                continue
            self.state = current
            if current == "hr":
                for hr in self._hr_users()[:1]:
                    self._todo(hr, _("ใบลาออก %s รอแผนกบุคคล", self.name))
            else:
                self._todo(user, _("อนุมัติใบลาออก %s", self.name))
            return
        self._goto_done()

    def action_submit(self):
        A = self.env["autozone.manpower.approver"]
        for rec in self.filtered(lambda r: r.state in ("draft", "rejected")):
            found = A.resolve(rec.department_id)
            root = A._root_department(rec.department_id)
            md = A._user_of(root.manager_id)
            manager = A.require(found["division_user"] or found["line_user"], found["division_employee"], "ผู้จัดการ")
            rec.write({"manager_user_id": manager.id, "gm_user_id": found["line_user"].id or md.id,
                       "md_user_id": md.id, "reject_reason": False,
                       "manager_date": False, "gm_date": False, "hr_date": False, "md_date": False})
            rec.state = "manager"
            rec._todo(manager, _("อนุมัติใบลาออก %s", rec.name))
        return True

    def _check_turn(self):
        self.ensure_one()
        if self.state == "hr":
            if not self.env.user.has_group("hr.group_hr_user") and not self.env.su:
                raise UserError(_("ขั้นนี้ให้แผนกบุคคลลงชื่อ"))
            return
        approver = self._approver()
        if self.env.user == approver or self.env.su:
            return
        if self.env["autozone.manpower.approver"].can_act_for_others(extra_group="hr.group_hr_manager"):
            self._message_log(body=_("%(me)s ลงชื่อแทน %(who)s", me=self.env.user.name, who=approver.name))
            return
        raise UserError(_("ใบลาออกนี้รอ %s ลงชื่อ", approver.name))

    def action_approve(self):
        order = [s for s, _label in STEPS]
        for rec in self.filtered(lambda r: r.state in order):
            rec._check_turn()
            rec.activity_ids.action_feedback(feedback=_("อนุมัติ"))
            step = rec.state
            vals = {step + "_date": fields.Date.context_today(self)}
            if step == "hr":
                vals["hr_user_id"] = self.env.uid
            rec.write(vals)
            nxt = order.index(step) + 1
            if nxt < len(order):
                rec._goto(order[nxt])
            else:
                rec._goto_done()
        return True

    def _goto_done(self):
        self.state = "approved"
        for hr in self._hr_users()[:1]:
            self._todo(hr, _("ลงลาออกในระบบ: %s", self.employee_id.name))
        # Start finding a replacement now, while the leaver is still working out
        # their notice — not on the last day.
        request = self.env["hr.manpower.request"]._az_draft_replacement(
            self.employee_id, self.date_last_day,
            _("ทดแทน %(who)s ลาออก ทำงานวันสุดท้าย %(day)s (ใบลาออก %(no)s)\nเหตุผลที่ลาออก: %(why)s",
              who=self.employee_id.name, day=self.date_last_day, no=self.name, why=self.reason),
            resignation=self)
        if request:
            self.manpower_request_id = request

    def action_reject(self):
        for rec in self:
            rec._check_turn()
            rec.activity_ids.action_feedback(feedback=_("ไม่อนุมัติ"))
            rec.write({"state": "rejected"})
            rec._message_log(body=_("ไม่อนุมัติโดย %s", self.env.user.name))
        return True

    def action_cancel(self):
        self.filtered(lambda r: r.state not in ("done",)).write({"state": "cancel"})
        self.activity_ids.action_feedback(feedback=_("ยกเลิก"))
        return True

    def action_reset_draft(self):
        self.filtered(lambda r: r.state in ("rejected", "cancel")).write({"state": "draft"})
        return True

    def action_register_departure(self):
        """Open Odoo's own departure dialog filled from this form — it archives
        the employee, closes the contract, and offers the blacklist tick."""
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("ใบลาออกต้องอนุมัติครบก่อน"))
        reason = self.env.ref("hr.departure_resigned", raise_if_not_found=False)
        return {
            "type": "ir.actions.act_window", "res_model": "hr.departure.wizard", "view_mode": "form",
            "target": "new", "name": _("ลงลาออก"),
            "context": {"active_id": self.employee_id.id, "toggle_active": True,
                        "default_employee_id": self.employee_id.id,
                        "default_departure_date": self.date_last_day,
                        "default_departure_reason_id": reason.id if reason else False,
                        "default_departure_description": _("ใบลาออก %(no)s: %(reason)s", no=self.name, reason=self.reason),
                        "az_resignation_id": self.id},
        }


class HrDepartureWizard(models.TransientModel):
    _inherit = "hr.departure.wizard"

    def action_register_departure(self):
        res = super().action_register_departure()
        rid = self.env.context.get("az_resignation_id")
        if rid:
            self.env["hr.resignation"].browse(rid).sudo().state = "done"
        else:
            self.env["hr.manpower.request"]._az_draft_replacement(
                self.employee_id, self.departure_date,
                _("ทดแทน %(who)s ออกจากงาน %(day)s (%(why)s)", who=self.employee_id.name,
                  day=self.departure_date, why=self.departure_reason_id.name or "-"))
        return res
