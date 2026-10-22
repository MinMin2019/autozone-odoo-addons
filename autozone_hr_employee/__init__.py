import re

from . import models

_THAI = re.compile(r"[\u0E00-\u0E7F]")


def post_init_hook(env):
    """Seed name_en for people whose name is already written in English.

    74 of the 451 active employees (mostly the Myanmar staff) were keyed with
    an English name only, so the English name is already there — it just sits
    in the wrong field. Thai names are left empty for HR to fill in.
    """
    employees = env["hr.employee"].with_context(active_test=False).search([("name_en", "=", False)])
    for employee in employees:
        if employee.name and not _THAI.search(employee.name):
            employee.name_en = employee.name
    # The migration for 18.0.1.2.0 only runs on an upgrade; a fresh install
    # needs the same one-off pass over the existing addresses.
    env["hr.employee"].with_context(active_test=False).search([])._az_normalize_private_address()
