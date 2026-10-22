from odoo import _, api, fields, models
from odoo.exceptions import UserError

# FM-HR-12 (Rev.01) — 5 ดีมาก · 4 ดี · 3 ปานกลาง · 2 แย่ · 1 แย่มาก
SCALE = [("5", "5 ดีมาก"), ("4", "4 ดี"), ("3", "3 ปานกลาง"), ("2", "2 แย่"), ("1", "1 แย่มาก")]
CRITERIA = [
    ("c01", "คุณภาพของงาน (Quality of work)"),
    ("c02", "ความสามารถในการปรับปรุงคุณภาพงาน (Ability of working improvement in quality)"),
    ("c03", "การแก้ไขปัญหาในงาน (Problem solving)"),
    ("c04", "ปริมาณงาน (Quantity of work)"),
    ("c05", "ความเร็วในการปฏิบัติงาน (Performance rapidity)"),
    ("c06", "ความละเอียดถี่ถ้วนในการปฏิบัติงาน (Performance fineness)"),
    ("c07", "ความสามารถในการเรียนรู้ (Learning ability)"),
    ("c08", "การจัดระบบการปฏิบัติงาน (Performance arrangement)"),
    ("c09", "ทักษะการสื่อสารระหว่างผู้ร่วมงาน (Inter colleague communication skill)"),
    ("c10", "ความคิดริเริ่มในการปฏิบัติงาน (Performance Creativeness)"),
]
PASS_MARK = 40


class OjtEvaluation(models.Model):
    """ใบประเมินผลการปฏิบัติงานหลังการฝึกอบรม OJT — FM-HR-12."""

    _name = "hr.ojt.evaluation"
    _description = "ใบประเมิน OJT"
    _inherit = ["mail.thread"]
    _order = "date_end desc, id desc"

    name = fields.Char(string="เลขที่", readonly=True, copy=False, default="ใหม่")
    state = fields.Selection([("draft", "ร่าง"), ("done", "ประเมินแล้ว")], default="draft", tracking=True)
    employee_id = fields.Many2one("hr.employee", string="ชื่อ (Name)", required=True, tracking=True)
    job_title = fields.Char(string="ตำแหน่ง (Position)", compute="_compute_from_employee", store=True, readonly=False)
    division_id = fields.Many2one("hr.department", string="ฝ่าย (Department)", compute="_compute_from_employee",
                                  store=True, readonly=False)
    department_id = fields.Many2one("hr.department", string="แผนก (Division)", compute="_compute_from_employee",
                                    store=True, readonly=False)
    date_start = fields.Date(string="ตั้งแต่วันที่ (Start Date)", required=True)
    date_end = fields.Date(string="ถึงวันที่ (To)", required=True)
    course = fields.Char(string="หัวข้อการฝึกอบรม (Training Course)", required=True)
    instructor = fields.Char(string="ผู้สอน (Instructor)")
    location = fields.Selection([("internal", "ภายในบริษัท (Internal)"), ("external", "ภายนอกบริษัท (External)")],
                                string="สถานที่ฝึกอบรม", default="internal")
    c01 = fields.Selection(SCALE, string=CRITERIA[0][1])
    c02 = fields.Selection(SCALE, string=CRITERIA[1][1])
    c03 = fields.Selection(SCALE, string=CRITERIA[2][1])
    c04 = fields.Selection(SCALE, string=CRITERIA[3][1])
    c05 = fields.Selection(SCALE, string=CRITERIA[4][1])
    c06 = fields.Selection(SCALE, string=CRITERIA[5][1])
    c07 = fields.Selection(SCALE, string=CRITERIA[6][1])
    c08 = fields.Selection(SCALE, string=CRITERIA[7][1])
    c09 = fields.Selection(SCALE, string=CRITERIA[8][1])
    c10 = fields.Selection(SCALE, string=CRITERIA[9][1])
    total = fields.Integer(string="คะแนนรวม (Total)", compute="_compute_total", store=True)
    result = fields.Selection([("pass", "ผ่าน (40 คะแนนขึ้นไป)"), ("fail", "ไม่ผ่าน (ต่ำกว่า 40 คะแนน)")],
                              string="สรุปผลการประเมิน", compute="_compute_total", store=True)
    comments = fields.Text(string="ข้อคิดเห็น (Comments)")
    follow_up = fields.Text(string="การติดตามผล (Follow Up)",
                            help="ใช้สำหรับกรณีที่พนักงานได้คะแนนรวมต่ำกว่า 40 คะแนน")
    evaluator_id = fields.Many2one("res.users", string="ผู้ประเมิน (Evaluator)", default=lambda self: self.env.user)
    eval_date = fields.Date(string="วัน/เดือน/ปี (Date)", default=fields.Date.context_today)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    @api.depends("employee_id")
    def _compute_from_employee(self):
        for rec in self:
            dept = rec.employee_id.department_id
            rec.job_title = rec.employee_id.job_title
            rec.department_id = dept
            rec.division_id = dept.division_id if "division_id" in dept._fields else dept.parent_id

    @api.depends(*[f for f, _label in CRITERIA])
    def _compute_total(self):
        for rec in self:
            scores = [int(rec[f]) for f, _label in CRITERIA if rec[f]]
            rec.total = sum(scores)
            rec.result = (("pass" if rec.total >= PASS_MARK else "fail")
                          if len(scores) == len(CRITERIA) else False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "ใหม่") == "ใหม่":
                number = self.env["ir.sequence"].next_by_code("hr.ojt.evaluation") or "0"
                vals["name"] = "OJT-%s-%s" % (fields.Date.context_today(self).year + 543, number)
        return super().create(vals_list)

    def action_done(self):
        for rec in self:
            if not rec.result:
                raise UserError(_("ให้คะแนนให้ครบ 10 หัวข้อก่อน"))
            if rec.result == "fail" and not rec.follow_up:
                raise UserError(_("คะแนนรวมต่ำกว่า 40 ต้องกรอกการติดตามผล (Follow Up)"))
            rec.state = "done"
        return True

    def action_draft(self):
        self.write({"state": "draft"})
        return True
