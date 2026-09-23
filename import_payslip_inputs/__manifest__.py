{
    'name': 'Custom Import Payslip Other Inputs',
    'version': '18.0.3.3.0',
    'category': 'Autozone/HR',
    'summary': 'Import Other Inputs (Allowance/Deduction) from Excel into Payslip Batch',
    'description': """
Phase 1: Legacy payroll import (Model A - pass-through)
=======================================================
- Import earnings/deductions from the legacy payroll system into Payslip Batches
  via Other Inputs (hr.payslip.input), following the standard Odoo payroll flow.
- Employees are matched strictly by Registration Number.
- Two-step wizard: validate + preview totals, then confirm (replace-all semantics).
- Ships a pass-through salary structure "Legacy Import" where every rule reads
  its amount from an input; the legacy system remains the calculation engine.
- Accounting: set Dr/Cr accounts on each salary rule and a journal on the
  structure (see doc/ACCOUNT_MAPPING.md).
    """,
    'author': 'Autozone',
    'depends': ['hr_payroll', 'hr_payroll_account'],
    'external_dependencies': {'python': ['openpyxl']},
    'data': [
        'security/ir.model.access.csv',
        'data/hr_payslip_input_type_data.xml',
        'data/hr_payroll_structure_data.xml',
        'data/hr_payroll_structure_v3.xml',
        'wizard/import_payslip_wizard_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_payslip_run_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
