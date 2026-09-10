# custom_invoice_print/__manifest__.py
{
    'name': 'Custom Invoice Print with Additional Details',
    'version': '18.0.1.3.0',
    'summary': 'Print Invoice 5 copies with different headers and additional details',
    'category': 'Autozone/Accounting',
    'author': 'Autozone',
    'website': 'https://www.yourwebsite.com',
    'license': 'LGPL-3',
    'depends': ['account', 'sale', 'autozone_report_fonts', 'autozone_base_address'],
    'data': [
        "security/ir.model.access.csv",
        'report/report_credit_note_action.xml',  # ต้องมาก่อน account_move_view.xml (ปุ่มพิมพ์อ้าง action นี้)
        'views/account_move_view.xml',
        "views/account_move_line_wizard_views.xml",
        "views/res_users_view.xml",
        'views/report_invoice_custom.xml',
        'views/report_credit_note_custom.xml',
        'views/report_invoice_form.xml',
        'report/report_action.xml',
        'report/report_invoice_form_action.xml',
    ],
    "assets": {
        "web.assets_backend": [
            "custom_invoice_print/static/src/css/invoice_line_button.css",
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

