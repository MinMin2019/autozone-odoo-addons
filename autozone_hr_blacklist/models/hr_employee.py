from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    no_rehire = fields.Boolean(
        string="ติด Blacklist ห้ามรับกลับ",
        tracking=True, copy=False, groups="hr.group_hr_user",
        help="ถ้าคนนี้สมัครเข้ามาใหม่ ระบบจะไม่ให้รับ — จับจากเลขบัตรประชาชน "
             "ชื่อ-นามสกุล เบอร์โทร หรืออีเมล ปลดได้เฉพาะ HR Manager",
    )
    no_rehire_reason = fields.Text(
        string="เหตุผลที่ติด Blacklist", tracking=True, copy=False, groups="hr.group_hr_user")
    no_rehire_date = fields.Date(string="วันที่ติด Blacklist", copy=False, groups="hr.group_hr_user")
    no_rehire_user_id = fields.Many2one(
        "res.users", string="ผู้บันทึก Blacklist", copy=False, groups="hr.group_hr_user")

    # ---------------------------------------------------------------- guards
    def _blacklist_hits(self, vals, exclude=None):
        return self.env["autozone.blacklist.matcher"]._find(
            name=vals.get("name"),
            id_card=vals.get("identification_id"),
            phones=(vals.get("private_phone"), vals.get("mobile_phone")),
            email=vals.get("private_email"),
            exclude=exclude,
        )

    def _raise_blacklisted(self, hits):
        raise UserError(_(
            "คนนี้ติด Blacklist ห้ามรับกลับเข้าทำงาน:\n%(who)s\n\n"
            "ถ้าเป็นคนละคนกัน (เช่นชื่อซ้ำ) หรือบริษัทอนุมัติให้รับแล้ว "
            "ให้ HR Manager เป็นผู้บันทึก",
            who=self.env["autozone.blacklist.matcher"]._describe(hits)))

    @api.model_create_multi
    def create(self, vals_list):
        matcher = self.env["autozone.blacklist.matcher"]
        overrides = []
        for vals in vals_list:
            hits = self._blacklist_hits(vals)
            if hits:
                if not matcher._is_override_allowed():
                    self._raise_blacklisted(hits)
                overrides.append(hits)
            else:
                overrides.append(None)
        employees = super().create(vals_list)
        for employee, hits in zip(employees, overrides):
            if hits and not self.env.su:
                # _message_log, not message_post: posting needs the user to have
                # an e-mail address, and a missing one must not block the hire.
                employee._message_log(body=_(
                    "สร้างโดย HR Manager ทั้งที่ตรงกับคนติด Blacklist: %s", ", ".join(hits.mapped("name"))))
        return employees

    def write(self, vals):
        matcher = self.env["autozone.blacklist.matcher"]
        manager = matcher._is_override_allowed()
        if "no_rehire" in vals and not vals["no_rehire"] and not manager:
            if any(e.no_rehire for e in self.sudo()):
                raise UserError(_("ปลด Blacklist ได้เฉพาะ HR Manager"))
        if vals.get("no_rehire"):
            vals = dict(vals, no_rehire_date=vals.get("no_rehire_date") or fields.Date.today(),
                        no_rehire_user_id=vals.get("no_rehire_user_id") or self.env.uid)
        if not manager:
            # Bringing the old record back is a re-hire too.
            if vals.get("active") and any(e.no_rehire and not e.active for e in self.sudo()):
                self._raise_blacklisted(self.sudo().filtered("no_rehire"))
            keys = {"name", "identification_id", "private_phone", "mobile_phone", "private_email"}
            if keys & vals.keys():
                for employee in self:
                    if employee.sudo().no_rehire:
                        continue
                    hits = self._blacklist_hits(vals, exclude=employee)
                    if hits:
                        self._raise_blacklisted(hits)
        return super().write(vals)
