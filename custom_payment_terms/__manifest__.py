# custom_payment_terms/__manifest__.py
{
    'name': 'Autozone Payment Terms',
    'version': '18.0.1.0.0',
    'summary': 'ชุด Payment Terms มาตรฐานของบริษัท (7 วันหลังรับของ / EOM+20/30/60 / โอนก่อนส่งของ)',
    'category': 'Autozone/Accounting',
    'author': 'Autozone',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'data/payment_terms.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
