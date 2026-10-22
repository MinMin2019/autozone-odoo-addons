import re

from odoo import _, api, models
from odoo.exceptions import UserError

# "ธวัช สวัสดิวร (รักษาการผู้จัดการฝ่าย)" — production keeps acting-role
# stand-ins as extra employee records with no login. The approval belongs to
# the real person behind it.
_ROLE_SUFFIX = re.compile(r"\s*\(.*\)\s*$")


class ManpowerApprover(models.AbstractModel):
    _name = "autozone.manpower.approver"
    _description = "Resolve approvers from the org chart"

    @api.model
    def _user_of(self, employee):
        """The login behind a manager slot, seeing through acting stand-ins."""
        employee = employee.sudo()
        if not employee:
            return self.env["res.users"]
        if employee.user_id:
            return employee.user_id
        base = _ROLE_SUFFIX.sub("", employee.name or "").strip()
        if base and base != employee.name:
            real = self.env["hr.employee"].sudo().search(
                [("name", "=", base), ("user_id", "!=", False)], limit=1)
            if real:
                return real.user_id
        return self.env["res.users"]

    @api.model
    def _root_department(self, department):
        chain = [int(i) for i in (department.sudo().parent_path or "").split("/") if i]
        return self.env["hr.department"].sudo().browse(chain[0]) if chain else department

    @api.model
    def resolve(self, department):
        """(ผู้จัดการฝ่าย, สายงาน/กรรมการ) as users, and the employees they stand for.

        ฝ่าย and สายงาน come from autozone_org_chart's division_id / line_id, which
        follow the department tree — so moving a department moves its approvers.
        A department above ฝ่าย level has no ฝ่าย manager; the สายงาน approves both
        steps. A สายงาน with no manager falls back to the managing director.
        """
        department = department.sudo()
        division = department.division_id
        line = department.line_id or self._root_department(department)
        division_mgr = division.manager_id if division else self.env["hr.employee"]
        line_mgr = line.manager_id or self._root_department(department).manager_id
        return {
            "division_user": self._user_of(division_mgr) or self._user_of(line_mgr),
            "division_employee": division_mgr or line_mgr,
            "line_user": self._user_of(line_mgr),
            "line_employee": line_mgr,
        }

    @api.model
    def hr_people(self, group_xmlid):
        """HR users to hand work to, best first.

        Whoever holds "อนุมัติแทนผู้อื่นได้" (the HR manager during roll-out),
        then members of `group_xmlid` who are real employees. OdooBot and other
        technical users sit in the admin groups too, and work given to them is
        work nobody sees.
        """
        technical = self.env.ref("base.user_root") | self.env.ref("base.public_user", raise_if_not_found=False)
        def real(users):
            return users.filtered(lambda u: u.active and not u.share and u not in technical and u.employee_ids)
        on_behalf = self.env.ref("autozone_hr_recruitment.group_approve_on_behalf", raise_if_not_found=False)
        first = real(on_behalf.sudo().users) if on_behalf else self.env["res.users"]
        return first | real(self.env.ref(group_xmlid).sudo().users)

    @api.model
    def notifiable(self, records):
        """records, ready for activity_schedule() by the current user.

        Scheduling an activity for someone else e-mails them "from" the current
        user, and Odoo refuses outright when that user has no e-mail address —
        which would turn an approval into an error. Without one, the activity is
        still created (it shows in the assignee's to-do list); only the e-mail
        is skipped.
        """
        if self.env.user.email:
            return records
        return records.with_context(mail_activity_quick_update=True)

    @api.model
    def can_act_for_others(self, extra_group=None):
        """Who may approve a step that is waiting on someone else.

        "อนุมัติแทนผู้อื่นได้" is its own group so HR can grant it during roll-out
        (approvers still learning the system) and take it away later without
        touching anyone's other rights. Every on-behalf approval is logged on the
        record by the caller.
        """
        user = self.env.user
        return bool(self.env.su
                    or user.has_group("autozone_hr_recruitment.group_approve_on_behalf")
                    or user.has_group("hr_recruitment.group_hr_recruitment_manager")
                    or (extra_group and user.has_group(extra_group)))

    @api.model
    def require(self, user, employee, step):
        if not user:
            raise UserError(_(
                "หาผู้อนุมัติขั้น \"%(step)s\" ไม่ได้: %(who)s ยังไม่มี login Odoo "
                "ให้ IT สร้าง user และผูกกับพนักงานก่อน",
                step=step, who=employee.name or _("ไม่ได้ตั้งผู้จัดการในผังองค์กร")))
        return user
