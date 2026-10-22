from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # FM-HR-04 asks for these and Odoo has no field for them; "เริ่มงาน" fills
    # them from the candidate.
    az_line_id = fields.Char(string="Line ID", groups="hr.group_hr_user")
    az_facebook = fields.Char(string="Facebook", groups="hr.group_hr_user")
    az_military = fields.Selection(
        [("not_yet", "ยังไม่เกณฑ์"), ("done", "เกณฑ์แล้ว"), ("exempt", "ได้รับการยกเว้น")],
        string="สถานภาพทางทหาร", groups="hr.group_hr_user")
    az_military_note = fields.Char(string="รายละเอียดทางทหาร", groups="hr.group_hr_user")
