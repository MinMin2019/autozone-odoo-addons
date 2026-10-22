from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from . import thai_text


class HrContract(models.Model):
    _inherit = "hr.contract"

    term_type = fields.Selection(
        [("indefinite", "ไม่มีกำหนดระยะเวลา"),
         ("fixed", "มีกำหนดระยะเวลา")],
        string="ประเภทสัญญาจ้าง",
        required=True, default="indefinite", tracking=True,
        help="มีกำหนดระยะเวลา: ต้องใส่วันสิ้นสุดสัญญา Odoo จะสร้างงานเตือน HR ก่อนครบกำหนด\n"
             "ไม่มีกำหนดระยะเวลา: ไม่ต้องใส่วันสิ้นสุด (Odoo ใส่ให้เองตอนปิดสัญญา)",
    )

    # --- what the paper contract asks for and Odoo had nowhere to keep ------
    sign_date = fields.Date(string="วันที่ทำสัญญา", default=fields.Date.context_today, tracking=True)
    sign_place = fields.Char(
        string="เขียนที่", default=lambda self: self.env.company.name,
        help="สถานที่ทำสัญญา พิมพ์ที่มุมขวาบนของสัญญา")
    witness_1 = fields.Char(string="พยานคนที่ 1")
    witness_2 = fields.Char(string="พยานคนที่ 2")
    probation_days = fields.Integer(
        string="ทดลองงาน (วัน)", default=119,
        help="กฎหมายแรงงานให้เลิกจ้างโดยไม่ต้องจ่ายค่าชดเชยได้ภายใน 119 วัน "
             "กรอกแล้ว Odoo คำนวณ End of Trial Period ให้")
    # Only the temporary-employee contract carries these four blanks.
    eval_probation_days = fields.Integer(string="ประเมินระหว่างทดลองงานทุก (วัน)")
    eval_after_days = fields.Integer(string="ประเมินหลังผ่านทดลองงานทุก (วัน)")
    renew_years = fields.Integer(string="ต่อสัญญาคราวละ (ปี)")
    renew_max_years = fields.Integer(string="ต่อเนื่องไม่เกิน (ปี)")

    # Only one direction is enforced. An indefinite contract still gets an end
    # date the day it is closed — hr_contract writes date_end itself when the
    # state goes to 'close' — so forbidding it would break every departure.
    @api.constrains("term_type", "date_end")
    def _check_term_type_end_date(self):
        for contract in self:
            if contract.term_type == "fixed" and not contract.date_end:
                raise ValidationError(_(
                    "สัญญาของ %s เป็นแบบมีกำหนดระยะเวลา ต้องใส่วันสิ้นสุดสัญญา",
                    contract.employee_id.name or contract.name))

    @api.onchange("date_start", "probation_days")
    def _onchange_probation_days(self):
        for contract in self:
            if contract.date_start and contract.probation_days > 0:
                contract.trial_date_end = contract.date_start + timedelta(days=contract.probation_days - 1)

    # --- helpers the printed contract calls ---------------------------------
    def az_thai_date(self, value):
        return thai_text.thai_date(value)

    def az_thai_number(self, value):
        return thai_text.thai_number(value) if value else ""

    def az_baht_text(self, amount):
        return thai_text.baht_text(amount) if amount else ""

    def az_contract_years(self):
        """Whole years from start to end, rounded — the paper says "N ปี"."""
        self.ensure_one()
        if not (self.date_start and self.date_end):
            return ""
        delta = relativedelta(self.date_end + timedelta(days=1), self.date_start)
        years = delta.years + (1 if delta.months >= 6 else 0)
        return str(years) if years else ""

    def az_employee_age(self):
        self.ensure_one()
        birthday = self.employee_id.sudo().birthday
        if not birthday:
            return ""
        on = self.sign_date or fields.Date.context_today(self)
        return str(relativedelta(on, birthday).years)

    def az_employee_title(self):
        """คำนำหน้า, kept by another production module (import_payslip_inputs)."""
        employee = self.employee_id.sudo()
        return (employee.title_th or "") if "title_th" in employee._fields else ""

    def az_private_address(self):
        """The paper splits the address into เลขที่/หมู่/ซอย/ถนน/ตำบล/อำเภอ/จังหวัด.
        Production keeps it as free text in private_street ("24/1 หมู่ที่ 1
        ต.คลองอุดมชลจร"), so it prints as one line rather than being guessed apart."""
        employee = self.employee_id.sudo()
        state = (employee.private_state_id.name or "").strip()
        if state and "กรุงเทพ" not in state and employee.private_state_id.country_id.code in (False, "TH"):
            state = "จ." + state
        parts = [employee.private_street, employee.private_street2, employee.private_city,
                 state, employee.private_zip]
        return " ".join(p.strip() for p in parts if p and p.strip())
