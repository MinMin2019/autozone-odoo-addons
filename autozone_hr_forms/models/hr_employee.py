from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # FM-HR-04 หน้า 3 — การขอความยินยอมใช้ข้อมูลส่วนตัว (ข้อมูลอ่อนไหว)
    az_consent_health = fields.Boolean(string="1. ข้อมูลสุขภาพ ประวัติการรักษาพยาบาล", groups="hr.group_hr_user", tracking=True)
    az_consent_criminal = fields.Boolean(string="2. ข้อมูลประวัติอาชญากรรม", groups="hr.group_hr_user", tracking=True)
    az_consent_biometric = fields.Boolean(string="3. ลายนิ้วมือหรือแบบจำลองใบหน้า (บันทึกเข้า-ออกงาน)",
                                          groups="hr.group_hr_user", tracking=True)
    az_consent_media = fields.Boolean(string="4. เผยแพร่รูปถ่าย/วีดีโอทางโซเชียลมีเดียของบริษัท",
                                      groups="hr.group_hr_user", tracking=True)
    az_consent_drug_test = fields.Boolean(string="5. ตรวจหาสารเสพติดในปัสสาวะ", groups="hr.group_hr_user", tracking=True)
    az_consent_date = fields.Date(string="วันที่ลงนามยินยอม", groups="hr.group_hr_user", tracking=True)

    az_resignation_ids = fields.One2many("hr.resignation", "employee_id", groups="hr.group_hr_user")
    az_ojt_ids = fields.One2many("hr.ojt.evaluation", "employee_id", groups="hr.group_hr_user")
    az_skillmap_ids = fields.One2many("hr.skillmap.evaluation", "employee_id", groups="hr.group_hr_user")
    az_ojt_count = fields.Integer(compute="_compute_az_form_counts", groups="hr.group_hr_user")
    az_skillmap_count = fields.Integer(compute="_compute_az_form_counts", groups="hr.group_hr_user")
    az_skillmap_this_year = fields.Integer(string="Skill Map ปีนี้ (ครั้ง)", compute="_compute_az_form_counts",
                                           groups="hr.group_hr_user", help="FM-HR-14: ประเมินอย่างน้อย 2 ครั้ง/ปี")

    @api.depends("az_ojt_ids", "az_skillmap_ids.date")
    def _compute_az_form_counts(self):
        year = fields.Date.context_today(self).year
        for employee in self:
            employee.az_ojt_count = len(employee.az_ojt_ids)
            employee.az_skillmap_count = len(employee.az_skillmap_ids)
            employee.az_skillmap_this_year = len(employee.az_skillmap_ids.filtered(lambda e: e.date and e.date.year == year))

    def _az_action(self, model, name):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": model, "name": name, "view_mode": "list,form",
                "domain": [("employee_id", "=", self.id)], "context": {"default_employee_id": self.id}}

    def action_az_open_ojt(self):
        return self._az_action("hr.ojt.evaluation", "ประเมิน OJT")

    def action_az_open_skillmap(self):
        return self._az_action("hr.skillmap.evaluation", "Skill Map")
