{
    'name': 'Custom WHT Consolidator',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'รวบรวมรายการภาษีหัก ณ ที่จ่ายหลายรายการเป็นใบ 50 ทวิ 1 ใบ',
    'depends': ['account', 'l10n_th_account_wht_cert_form'], # ต้องเรียกใช้แอปบัญชีและแอปภาษีไทยของ OCA
    'data': [
        'security/ir.model.access.csv',
        'views/wht_consolidate_wizard_view.xml',
    ],
    'installable': True,
    'application': False,
}