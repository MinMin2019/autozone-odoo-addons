from odoo import fields, models

STEPS = [
    ("new", "ใหม่"),
    ("screen", "คัดกรอง"),
    ("interview", "สัมภาษณ์"),
    ("evaluate", "ประเมินผล"),
    ("hire_approval", "รออนุมัติจ้าง"),
    ("onboarding", "นัดเริ่มงาน"),
    ("hired", "เริ่มงานแล้ว"),
]


class RecruitmentStage(models.Model):
    _inherit = "hr.recruitment.stage"

    # What a stage means in HR's flow, independent of its (editable) name, so
    # the hire-approval gate keeps working if HR renames or reorders stages.
    az_step = fields.Selection(STEPS, string="ขั้นใน Flow สรรหา")
