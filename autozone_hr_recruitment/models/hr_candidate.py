from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

# FM-HR-04 rates trade skills and languages on the same 0–3 scale.
CRAFT_LEVELS = [("0", "0 ไม่เป็น"), ("1", "1 ซ่อมเบาได้"), ("2", "2 ซ่อมกลางได้"), ("3", "3 ซ่อมหนักได้")]
LANG_LEVELS = [("0", "0 ไม่ได้"), ("1", "1 อ่อน"), ("2", "2 พอใช้"), ("3", "3 ดี")]
CRAFTS = [
    ("az_craft_beat", "เคาะ"), ("az_craft_strip", "รื้อ"), ("az_craft_assemble", "ประกอบ"),
    ("az_craft_putty", "โป๊ว"), ("az_craft_prep", "เตรียมพื้น"), ("az_craft_mix", "ผสมสี"),
    ("az_craft_spray", "พ่นสี"), ("az_craft_polish", "ขัดสี"),
]


class HrCandidate(models.Model):
    """ใบสมัครงาน FM-HR-04 (Rev.04) — everything the paper form asks of the person.

    It lives on the candidate, not the application: one person applying to two
    positions fills the form once. "เริ่มงาน" copies it onto the employee.
    """

    _inherit = "hr.candidate"

    az_photo = fields.Image(string="รูปถ่าย", max_width=512, max_height=512)
    az_title = fields.Selection([("นาย", "นาย"), ("นาง", "นาง"), ("นางสาว", "นางสาว")], string="คำนำหน้า")
    az_birthday = fields.Date(string="วันเกิด")
    az_age = fields.Integer(string="อายุ (ปี)", compute="_compute_az_age")
    az_nationality_id = fields.Many2one("res.country", string="สัญชาติ",
                                        default=lambda self: self.env.ref("base.th", raise_if_not_found=False))

    # 1. ที่อยู่ปัจจุบัน — split the way the form splits it
    az_addr_no = fields.Char(string="เลขที่")
    az_addr_moo = fields.Char(string="หมู่ที่")
    az_addr_soi = fields.Char(string="ตรอก/ซอย")
    az_addr_road = fields.Char(string="ถนน")
    az_addr_tambon = fields.Char(string="ตำบล")
    az_addr_amphoe = fields.Char(string="อำเภอ")
    az_addr_state_id = fields.Many2one(
        "res.country.state", string="จังหวัด",
        domain="[('country_id.code', '=', 'TH'), '!', ('code', '=like', 'TH-%')]")
    az_addr_zip = fields.Char(string="รหัสไปรษณีย์")
    az_line_id = fields.Char(string="Line ID")
    az_facebook = fields.Char(string="Facebook")

    # 2. สถานะทางครอบครัว
    az_marital = fields.Selection([("single", "โสด"), ("married", "สมรส"), ("divorced", "หย่า")],
                                  string="สถานะทางครอบครัว")
    az_marriage_registered = fields.Selection([("yes", "จดทะเบียนสมรส"), ("no", "ไม่ได้จดทะเบียน")],
                                              string="การจดทะเบียน")
    az_emergency_name = fields.Char(string="ผู้ติดต่อกรณีเร่งด่วน")
    az_emergency_relation = fields.Char(string="ความสัมพันธ์")
    az_emergency_phone = fields.Char(string="เบอร์โทรผู้ติดต่อ")

    # 3. สถานภาพทางทหาร
    az_military = fields.Selection(
        [("not_yet", "ยังไม่เกณฑ์"), ("done", "เกณฑ์แล้ว"), ("exempt", "ได้รับการยกเว้น")],
        string="สถานภาพทางทหาร")
    az_military_draft_when = fields.Char(string="ถูกเกณฑ์เมื่อ")
    az_military_unit = fields.Char(string="สังกัด")
    az_military_date = fields.Char(string="วันที่เข้าประจำการ")
    az_military_exempt_reason = fields.Char(string="ยกเว้นเพราะ")

    # 4. ประวัติการศึกษาสูงสุด
    az_education = fields.Selection(
        [("primary", "ประถมศึกษา"), ("m3", "มัธยมต้น (ม.3)"), ("m6", "มัธยมปลาย (ม.6)"),
         ("vocational", "ปวช."), ("high_vocational", "ปวส."), ("bachelor", "ปริญญาตรี"),
         ("master", "ปริญญาโท"), ("doctor", "ปริญญาเอก"), ("other", "อื่น ๆ")],
        string="วุฒิการศึกษา")
    az_school = fields.Char(string="สถานศึกษาสูงสุด")
    az_gpa = fields.Char(string="เกรดเฉลี่ย")

    # 5. ประวัติการทำงาน
    az_work_history_ids = fields.One2many("hr.candidate.work.history", "candidate_id", string="ประวัติการทำงาน")

    # ความสามารถช่าง (เฉพาะตำแหน่งช่างฝีมือ)
    az_craft_beat = fields.Selection(CRAFT_LEVELS, string="เคาะ")
    az_craft_strip = fields.Selection(CRAFT_LEVELS, string="รื้อ")
    az_craft_assemble = fields.Selection(CRAFT_LEVELS, string="ประกอบ")
    az_craft_putty = fields.Selection(CRAFT_LEVELS, string="โป๊ว")
    az_craft_prep = fields.Selection(CRAFT_LEVELS, string="เตรียมพื้น")
    az_craft_mix = fields.Selection(CRAFT_LEVELS, string="ผสมสี")
    az_craft_spray = fields.Selection(CRAFT_LEVELS, string="พ่นสี")
    az_craft_polish = fields.Selection(CRAFT_LEVELS, string="ขัดสี")
    az_trade_test_level = fields.Char(string="สอบระดับฝีมือ: ระดับ")
    az_trade_test_field = fields.Char(string="สาขาวิชา")
    az_trade_test_institute = fields.Char(string="สถาบัน")

    # 6. ความสามารถทางภาษา
    az_language_ids = fields.One2many("hr.candidate.language", "candidate_id", string="ความสามารถทางภาษา",
                                      default=lambda self: [(0, 0, {"name": "ไทย"}), (0, 0, {"name": "อังกฤษ"})])

    # 7. รายละเอียดอื่น ๆ
    az_has_relative = fields.Selection([("no", "ไม่มี"), ("yes", "มี")], string="ญาติ/คนรู้จักทำงานที่บริษัท")
    az_relative_ids = fields.One2many("hr.candidate.relative", "candidate_id", string="ญาติ/คนรู้จักในบริษัท")
    az_criminal_check_consent = fields.Selection([("yes", "ยินยอม"), ("no", "ไม่ยินยอม")],
                                                 string="ยินยอมให้ตรวจประวัติอาชญากรรม")
    az_application_date = fields.Date(string="วันที่สมัคร", default=fields.Date.context_today)

    @api.depends("az_birthday")
    def _compute_az_age(self):
        today = fields.Date.context_today(self)
        for candidate in self:
            candidate.az_age = relativedelta(today, candidate.az_birthday).years if candidate.az_birthday else 0

    def _az_street(self):
        """เลขที่ หมู่ ซอย ถนน ต.ตำบล — one line, the shape the employee address uses."""
        self.ensure_one()
        parts = [
            self.az_addr_no,
            self.az_addr_moo and "ม.%s" % self.az_addr_moo,
            self.az_addr_soi and "ซ.%s" % self.az_addr_soi,
            self.az_addr_road and "ถ.%s" % self.az_addr_road,
            self.az_addr_tambon and "ต.%s" % self.az_addr_tambon,
        ]
        return " ".join(p for p in parts if p)

    def _az_employee_vals(self):
        """FM-HR-04 data in the employee's own fields, for "เริ่มงาน"."""
        self.ensure_one()
        certificate = {"bachelor": "bachelor", "master": "master", "doctor": "doctor"}.get(self.az_education)
        if self.az_education and not certificate:
            certificate = "graduate" if self.az_education in ("m6", "vocational", "high_vocational") else "other"
        vals = {
            "birthday": self.az_birthday,
            "country_id": self.az_nationality_id.id,
            "identification_id": self.identification_id,
            "private_street": self._az_street() or False,
            "private_city": self.az_addr_amphoe or False,
            "private_state_id": self.az_addr_state_id.id,
            "private_zip": self.az_addr_zip or False,
            "private_country_id": self.az_addr_state_id.country_id.id,
            "private_phone": self.partner_phone,
            "private_email": self.email_from,
            "marital": self.az_marital or "single",
            "emergency_contact": " ".join(p for p in (self.az_emergency_name, self.az_emergency_relation and "(%s)" % self.az_emergency_relation) if p) or False,
            "emergency_phone": self.az_emergency_phone,
            "certificate": certificate,
            "study_school": self.az_school,
            "az_line_id": self.az_line_id,
            "az_facebook": self.az_facebook,
            "az_military": self.az_military,
            "az_military_note": " ".join(p for p in (self.az_military_draft_when, self.az_military_unit,
                                                     self.az_military_date, self.az_military_exempt_reason) if p) or False,
        }
        if self.az_photo:
            vals["image_1920"] = self.az_photo
        if "title_th" in self.env["hr.employee"]._fields and self.az_title:
            vals["title_th"] = self.az_title
        return {k: v for k, v in vals.items() if v not in (None, False, "") or k in ("marital",)}


class CandidateWorkHistory(models.Model):
    _name = "hr.candidate.work.history"
    _description = "ประวัติการทำงาน (FM-HR-04 ข้อ 5)"
    _order = "sequence, id"

    candidate_id = fields.Many2one("hr.candidate", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    period = fields.Char(string="จาก – ถึง")
    company = fields.Char(string="ชื่อสถานที่ทำงาน", required=True)
    position = fields.Char(string="ตำแหน่ง")
    salary = fields.Float(string="เงินเดือน")
    leave_reason = fields.Char(string="สาเหตุที่ออก")


class CandidateLanguage(models.Model):
    _name = "hr.candidate.language"
    _description = "ความสามารถทางภาษา (FM-HR-04 ข้อ 6)"
    _order = "id"

    candidate_id = fields.Many2one("hr.candidate", required=True, ondelete="cascade")
    name = fields.Char(string="ภาษา", required=True)
    # level_* rather than write/read, which would shadow the ORM methods
    level_understand = fields.Selection(LANG_LEVELS, string="เข้าใจ")
    level_speak = fields.Selection(LANG_LEVELS, string="พูด")
    level_write = fields.Selection(LANG_LEVELS, string="เขียน")
    level_read = fields.Selection(LANG_LEVELS, string="อ่าน")


class CandidateRelative(models.Model):
    _name = "hr.candidate.relative"
    _description = "ญาติ/คนรู้จักในบริษัท (FM-HR-04 ข้อ 7.1)"

    candidate_id = fields.Many2one("hr.candidate", required=True, ondelete="cascade")
    name = fields.Char(string="ชื่อ – สกุล", required=True)
    relation = fields.Char(string="ความสัมพันธ์")
    branch = fields.Char(string="สาขา")
