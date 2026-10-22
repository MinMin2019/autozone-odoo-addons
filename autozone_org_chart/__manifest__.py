{
    "name": "Autozone Org Chart",
    "summary": "Org chart cards that read like FM-HR-36, visible vacancies, "
               "and the analytic account that ties a branch to its books",
    "description": """
Autozone Org Chart
==================

Four changes, all driven by how บริษัท ออโต้โซน จำกัด actually reads its own
FM-HR-36 chart:

1. Job title above the name on the employee org chart, as on the paper chart.
   Patched on BOTH hierarchy views — hr.employee (HR officers) and
   hr.employee.public (everyone else) — because they ship identical card
   markup and patching one makes the chart depend on who is logged in.

2. A "ตำแหน่งว่าง" badge on the department org chart wherever a department has
   no manager. Departments exist without managers, so that chart is where a
   vacancy can be seen at all; the employee chart simply omits it.

3. A second-role line for people wearing two hats. Computed from the
   departments they manage, so it never needs retyping. Odoo cannot show one
   employee twice — parent_id is a many2one and hr.employee carries
   unique(user_id, company_id) — so the second hat is shown, not duplicated.

4. analytic_account_id on hr.department, meant for the branch level only.
   Reporting lines follow reassignments while the branch keeps posting to the
   analytic account for its geography; this field is the single joint between
   those two hierarchies.
""",
    "version": "18.0.1.4.0",
    "license": "LGPL-3",
    "author": "Autozone IT",
    "category": "Autozone/HR",
    "depends": [
        "hr_org_chart",            # owns both employee hierarchy views and the department one
        "analytic",                # account.analytic.account
        "hr_contract",             # the contract form gets the same job / department pickers
        # Adds an "Approval Level" group loose in the department sheet. Declared
        # so its view is guaranteed to have been applied before this module moves
        # that group into a tab beside Job Positions.
        "l10n_th_tier_department",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_employee_views.xml",
        "views/hr_department_views.xml",
        "views/hr_job_views.xml",
        "views/hr_contract_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "auto_install": False,
    "application": False,
}
