from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# FM-HR-14 (REV.03) ระดับ — A,B ผ่าน · C,D ไม่ผ่าน · ผ่านทดลองงานที่ Skill ≥ 75%
LEVELS = [
    ("A", "A 90–100% ปฏิบัติงานได้ตามมาตรฐาน สอนงานผู้อื่นได้"),
    ("B", "B 75–89% เข้าใจเนื้อหางานและมาตรฐานการทำงาน"),
    ("C", "C 50–74% เข้าใจแต่ต้องมีหัวหน้าคอยดูแลและให้คำแนะนำ"),
    ("D", "D 25–49% ได้รับการฝึกอบรมแล้ว แต่ยังไม่ค่อยเข้าใจมาตรฐาน หัวหน้าต้องดูแลใกล้ชิด"),
    ("E", "E 0–24% อยู่ระหว่างการอบรม และประเมินขีดความสามารถ"),
]
PROBATION_TARGET = 75.0


def level_of(percent):
    if percent >= 90:
        return "A"
    if percent >= 75:
        return "B"
    if percent >= 50:
        return "C"
    if percent >= 25:
        return "D"
    return "E"


class SkillmapTask(models.Model):
    """หัวข้อหลักสูตร / Skill / Task ของตำแหน่งงาน — the columns of the Skill Map chart."""

    _name = "hr.skillmap.task"
    _description = "Skill Map: หัวข้อ Skill / Task"
    _order = "job_id, sequence, id"

    job_id = fields.Many2one("hr.job", string="ตำแหน่งงาน", required=True, index=True, ondelete="cascade")
    name = fields.Char(string="หัวข้อหลักสูตร / Skill / Task", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class SkillmapEvaluation(models.Model):
    """One ครั้งที่ of FM-HR-14 for one employee — ประเมินอย่างน้อย 2 ครั้ง/ปี."""

    _name = "hr.skillmap.evaluation"
    _description = "Skill Map: การประเมิน"
    _inherit = ["mail.thread"]
    _order = "date desc, id desc"

    employee_id = fields.Many2one("hr.employee", string="ชื่อ - สกุล", required=True, index=True, tracking=True)
    registration_number = fields.Char(related="employee_id.registration_number", string="รหัสพนักงาน")
    date_start_work = fields.Date(related="employee_id.first_contract_date", string="วันที่เริ่มงาน")
    job_id = fields.Many2one("hr.job", string="ตำแหน่งงาน", required=True, compute="_compute_job", store=True,
                             readonly=False)
    department_id = fields.Many2one(related="employee_id.department_id", string="หน่วยงาน", store=True)
    round_no = fields.Integer(string="ครั้งที่", compute="_compute_round", store=True, readonly=False)
    date = fields.Date(string="วันที่ประเมิน", default=fields.Date.context_today, required=True)
    evaluator_id = fields.Many2one("res.users", string="ผู้ประเมิน", default=lambda self: self.env.user)
    line_ids = fields.One2many("hr.skillmap.evaluation.line", "evaluation_id", string="ผลประเมินแต่ละหัวข้อ")
    score = fields.Float(string="คะแนนเฉลี่ย (%)", compute="_compute_score", store=True, digits=(5, 1))
    level = fields.Selection(LEVELS, string="ระดับรวม", compute="_compute_score", store=True)
    probation_pass = fields.Boolean(string="ผ่านเป้าทดลองงาน (≥ 75%)", compute="_compute_score", store=True)
    note = fields.Text(string="หมายเหตุ", help="กรณีมีพนักงานสับเปลี่ยน / โยกย้าย ให้ระบุ")
    state = fields.Selection([("draft", "ร่าง"), ("done", "ประเมินแล้ว")], default="draft", tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    @api.depends("employee_id")
    def _compute_job(self):
        for rec in self:
            if rec.employee_id.job_id:
                rec.job_id = rec.employee_id.job_id

    @api.depends("employee_id", "job_id")
    def _compute_round(self):
        for rec in self:
            if not rec.round_no and rec.employee_id:
                previous = self.search_count([("employee_id", "=", rec.employee_id.id), ("job_id", "=", rec.job_id.id),
                                              ("id", "!=", rec._origin.id or 0)])
                rec.round_no = previous + 1

    @api.depends("line_ids.score")
    def _compute_score(self):
        for rec in self:
            lines = rec.line_ids
            avg = sum(lines.mapped("score")) / len(lines) if lines else 0.0
            rec.score = avg
            rec.level = level_of(avg) if lines else False
            rec.probation_pass = bool(lines) and avg >= PROBATION_TARGET

    @api.onchange("job_id")
    def _onchange_job_lines(self):
        if self.job_id and not self.line_ids:
            tasks = self.env["hr.skillmap.task"].search([("job_id", "=", self.job_id.id)])
            self.line_ids = [(0, 0, {"task_id": t.id}) for t in tasks]

    @api.model_create_multi
    def create(self, vals_list):
        # job_id is required and follows the employee; a stored compute runs
        # after the insert, so fill it here for creates that leave it out.
        for vals in vals_list:
            if not vals.get("job_id") and vals.get("employee_id"):
                vals["job_id"] = self.env["hr.employee"].browse(vals["employee_id"]).job_id.id
        records = super().create(vals_list)
        for rec in records.filtered(lambda r: not r.line_ids and r.job_id):
            tasks = self.env["hr.skillmap.task"].search([("job_id", "=", rec.job_id.id)])
            rec.line_ids = [(0, 0, {"task_id": t.id}) for t in tasks]
        return records

    def action_done(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("ตำแหน่ง %s ยังไม่มีหัวข้อ Skill / Task — ตั้งที่เมนู ตั้งค่า Skill Map ก่อน", rec.job_id.name))
            rec.state = "done"
        return True

    def action_draft(self):
        self.write({"state": "draft"})
        return True


class SkillmapEvaluationLine(models.Model):
    _name = "hr.skillmap.evaluation.line"
    _description = "Skill Map: คะแนนแต่ละหัวข้อ"
    _order = "evaluation_id, task_sequence, id"

    evaluation_id = fields.Many2one("hr.skillmap.evaluation", required=True, ondelete="cascade", index=True)
    task_id = fields.Many2one("hr.skillmap.task", string="Skill / Task", required=True)
    task_sequence = fields.Integer(related="task_id.sequence", store=True)
    score = fields.Float(string="Eva. Skill (%)", digits=(5, 1))
    level = fields.Selection(LEVELS, string="ระดับ", compute="_compute_level", store=True)
    passed = fields.Boolean(string="ผ่าน (A, B)", compute="_compute_level", store=True)
    # Flattened for the Skill Map Chart pivot (rows: employee, columns: task).
    employee_id = fields.Many2one(related="evaluation_id.employee_id", store=True, string="พนักงาน")
    job_id = fields.Many2one(related="evaluation_id.job_id", store=True, string="ตำแหน่งงาน")
    department_id = fields.Many2one(related="evaluation_id.department_id", store=True, string="หน่วยงาน")
    round_no = fields.Integer(related="evaluation_id.round_no", store=True, string="ครั้งที่")
    date = fields.Date(related="evaluation_id.date", store=True, string="วันที่ประเมิน")

    _sql_constraints = [("score_range", "CHECK(score >= 0 AND score <= 100)", "คะแนนต้องอยู่ระหว่าง 0–100%")]

    @api.constrains("score")
    def _check_score(self):
        for line in self:
            if not 0 <= (line.score or 0) <= 100:
                raise ValidationError(_("คะแนน Eva. Skill ต้องอยู่ระหว่าง 0–100%"))

    @api.depends("score")
    def _compute_level(self):
        for line in self:
            line.level = level_of(line.score or 0.0)
            line.passed = line.level in ("A", "B")
