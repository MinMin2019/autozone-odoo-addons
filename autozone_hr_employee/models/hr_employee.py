import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from . import thai_address


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    name_en = fields.Char(
        string="ชื่อ-นามสกุล (อังกฤษ)", tracking=True,
        help="ชื่อตามหนังสือเดินทางหรือบัตรประชาชนด้านหลัง เช่น Somchai Jaidee",
    )

    # The temporary-employee contract asks for these three; Odoo stores the
    # ID number only.
    id_card_issue_place = fields.Char(string="บัตรออกให้ ณ", groups="hr.group_hr_user")
    id_card_issue_date = fields.Date(string="วันออกบัตร", groups="hr.group_hr_user")
    id_card_expiry_date = fields.Date(string="บัตรหมดอายุ", groups="hr.group_hr_user")

    # --- บัญชีธนาคารรับเงินเดือน (เฉพาะ HR) ---------------------------------
    # Odoo's own bank_account_id is a res.partner.bank on the employee's work
    # contact — the same records Accounting keeps for vendors and customers, so
    # anyone with accounting rights sees every employee's account. Autozone
    # pays salaries outside Odoo, so these plain fields are visible to HR
    # officers only and never reach Contacts or Accounting.
    hr_bank_name = fields.Selection(
        [("BBL", "กรุงเทพ"), ("KBANK", "กสิกรไทย"), ("KTB", "กรุงไทย"), ("SCB", "ไทยพาณิชย์"),
         ("BAY", "กรุงศรีอยุธยา"), ("TTB", "ทหารไทยธนชาต"), ("GSB", "ออมสิน"), ("BAAC", "ธ.ก.ส."),
         ("GHB", "อาคารสงเคราะห์"), ("UOB", "ยูโอบี"), ("CIMBT", "ซีไอเอ็มบี ไทย"),
         ("KKP", "เกียรตินาคินภัทร"), ("LHB", "แลนด์ แอนด์ เฮ้าส์"), ("TISCO", "ทิสโก้"),
         ("IBANK", "อิสลามแห่งประเทศไทย"), ("OTHER", "อื่น ๆ")],
        string="ธนาคาร", groups="hr.group_hr_user", tracking=True)
    hr_bank_account_no = fields.Char(string="เลขที่บัญชี", groups="hr.group_hr_user", tracking=True)
    hr_bank_account_name = fields.Char(
        string="ชื่อบัญชี", groups="hr.group_hr_user", tracking=True,
        help="ชื่อเจ้าของบัญชีตามสมุดบัญชี ถ้าไม่ตรงกับชื่อพนักงาน ธนาคารอาจโอนไม่ผ่าน")
    hr_bank_branch = fields.Char(string="สาขาธนาคาร", groups="hr.group_hr_user")

    @api.constrains("hr_bank_account_no")
    def _check_hr_bank_account_no(self):
        for employee in self:
            number = employee.hr_bank_account_no
            if number and not re.fullmatch(r"\d{10,15}", re.sub(r"[\s-]", "", number)):
                raise ValidationError(_(
                    "เลขที่บัญชีของ %s ต้องเป็นตัวเลข 10–15 หลัก (ใส่ขีดหรือเว้นวรรคได้)", employee.name))

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees._az_normalize_private_address()
        return employees

    def write(self, vals):
        res = super().write(vals)
        if {"private_city", "private_state_id"} & vals.keys() and not self.env.context.get("az_address_normalizing"):
            self._az_normalize_private_address()
        return res

    def _az_normalize_private_address(self):
        """Thai province instead of the English one, and อ./เขต on the district."""
        changed = 0
        for employee in self.sudo():
            state = thai_address.thai_state_for(self.env, employee.private_state_id)
            city = thai_address.normalize_city(employee.private_city, state)
            vals = {}
            if state != employee.private_state_id:
                vals["private_state_id"] = state.id
            if city != employee.private_city:
                vals["private_city"] = city
            if vals:
                employee.with_context(az_address_normalizing=True).write(vals)
                changed += 1
        return changed


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    # hr.employee.public is a SQL view over hr_employee built from the stored
    # fields declared here, so declaring it is what lets non-HR users see it.
    name_en = fields.Char(readonly=True)
