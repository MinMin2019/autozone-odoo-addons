import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """One pass over every employee, archived included, on upgrade to 1.2.0."""
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False, "tracking_disable": True})
    employees = env["hr.employee"].search(["|", ("private_city", "!=", False), ("private_state_id", "!=", False)])
    changed = employees._az_normalize_private_address()
    _logger.info("autozone_hr_employee: normalized private address on %s of %s employees",
                 changed, len(employees))
