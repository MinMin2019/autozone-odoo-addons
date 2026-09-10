{
    'name': 'Custom Receipt Vat and Non Vat',
    'version': '18.0.1.1.0',
    'category': 'Autozone/Accounting',
    'summary': 'เพิ่มฟิลด์ข้อมูลรถยนต์และงานซ่อมในใบเสร็จรับเงิน',
    'author': 'Autozone',
    'depends': ['account', 'autozone_base_address'], # ต้องอ้างอิงโมดูล account
    'data': [
        'data/account_journal_data.xml',
        'views/account_move_views.xml',
        'views/report_garage_receipt.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
