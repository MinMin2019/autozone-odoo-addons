import re

from odoo import _, api, models

# The same honorifics the HR spreadsheets carry and Odoo names do not — see the
# org-chart migration, where a name join without stripping them silently failed.
_PREFIX = re.compile(
    r"^(นาย|นางสาว|น\.ส\.|นาง|คุณ|ว่าที่\s*ร\.?ต\.?|mrs\.?|mr\.?|ms\.?|miss)\s*", re.I)


def norm_name(value):
    value = _PREFIX.sub("", (value or "").strip())
    # Drop an acting-role suffix such as "(รักษาการผู้จัดการฝ่าย)" and every space,
    # since double spaces between first and last name are common in the source data.
    value = re.sub(r"\(.*?\)", "", value)
    return re.sub(r"\s+", "", value).lower()


def norm_id_card(value):
    digits = re.sub(r"\D", "", value or "")
    return digits if len(digits) >= 10 else ""


def norm_phone(value):
    digits = re.sub(r"\D", "", value or "")
    # +66 81 234 5678 and 081-234-5678 are the same number; compare the last 9.
    return digits[-9:] if len(digits) >= 9 else ""


def norm_email(value):
    return (value or "").strip().lower()


class BlacklistMatcher(models.AbstractModel):
    _name = "autozone.blacklist.matcher"
    _description = "Match people against the no-rehire list"

    @api.model
    def _is_override_allowed(self):
        return self.env.su or self.env.user.has_group("hr.group_hr_manager")

    @api.model
    def _blacklisted_employees(self):
        return self.env["hr.employee"].sudo().with_context(active_test=False).search(
            [("no_rehire", "=", True)])

    @api.model
    def _find(self, name=None, id_card=None, phones=(), email=None, exclude=None):
        """Blacklisted employees that look like this person.

        ID card number first — it is the only key that cannot belong to
        someone else. Name, phone and e-mail catch the applicant who has not
        given an ID number yet; a namesake will be caught too, which is why an
        HR Manager can always override.
        """
        want = {
            "id": norm_id_card(id_card),
            "name": norm_name(name),
            "phones": {p for p in map(norm_phone, phones) if p},
            "email": norm_email(email),
        }
        found = self.env["hr.employee"].sudo()
        for emp in self._blacklisted_employees():
            if exclude and emp in exclude:
                continue
            emp_phones = {p for p in map(norm_phone, (emp.private_phone, emp.mobile_phone)) if p}
            if ((want["id"] and want["id"] == norm_id_card(emp.identification_id))
                    or (want["name"] and want["name"] == norm_name(emp.name))
                    or (want["phones"] & emp_phones)
                    or (want["email"] and want["email"] == norm_email(emp.private_email))):
                found |= emp
        return found

    @api.model
    def _describe(self, employees):
        lines = []
        for emp in employees:
            lines.append(_(
                "• %(name)s (รหัส %(code)s) ออกเมื่อ %(date)s — %(reason)s",
                name=emp.name, code=emp.registration_number or "-",
                date=emp.departure_date or "-", reason=emp.no_rehire_reason or "-"))
        return "\n".join(lines)
