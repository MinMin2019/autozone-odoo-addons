from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    managed_department_ids = fields.One2many(
        comodel_name="hr.department",
        inverse_name="manager_id",
        string="Departments Managed",
        help="Every department this person is the manager of. A department "
             "manager does not have to belong to the department they manage, "
             "which is what makes a second hat expressible at all.",
    )

    second_role_label = fields.Char(
        string="Second Role",
        compute="_compute_second_role_label",
        store=True,
        help="The departments this person manages, excluding their own. Odoo "
             "cannot draw one employee in two places — the org chart walks a "
             "single many2one — so the second hat is labelled rather than "
             "duplicated.",
    )

    @api.depends("managed_department_ids", "managed_department_ids.name", "department_id")
    def _compute_second_role_label(self):
        for employee in self:
            extra = employee.managed_department_ids.filtered(
                lambda d: d != employee.department_id
            )
            employee.second_role_label = " · ".join(extra.mapped("name")) or False


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    # hr.employee.public is a SQL view over hr_employee, rebuilt from every
    # stored non-x2many field declared on the model (see hr_employee_public.
    # _get_fields), and its ids are hr_employee's ids. Declaring the column
    # here is all it takes for the same value to reach users without HR
    # rights — who are the ones actually reading the org chart.
    second_role_label = fields.Char(readonly=True)
