{
    'name': 'Custom Thai Accounting Vouchers',
    'version': '18.0.1.4.1',
    'category': 'Autozone/Accounting',
    'summary': 'Separate RV, PV, JV menus for Thai Accounting',
    'author': 'Autozone',
    'depends': ['account', 'purchase', 'autozone_base_address'],
    'data': [
        'data/account_journal_data.xml',
        'views/account_move_views.xml',
        'views/report_payment_voucher.xml',
    ],
    'installable': True,
    'application': False,
}
