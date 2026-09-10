# custom_due_date_display/__manifest__.py
{
    'name': 'Show Due Date with Payment Terms',
    'version': '18.0.1.0.0',
    'summary': 'แสดงวันครบกำหนดชำระบนฟอร์มใบแจ้งหนี้/บิล แม้เลือก Payment Terms แล้ว',
    'category': 'Autozone/Accounting',
    'author': 'Autozone',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
