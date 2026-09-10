{
    'name': 'Custom Vendor Payment Report',
    'version': '18.0.1.0.0',
    'category': 'Autozone/Accounting',
    'summary': 'รายงานการชำระเงิน สำหรับเช็คใบวางบิลจาก Vendor (AP)',
    'description': """
        โมดูลจัดทำรายงานการชำระเงินฝั่งเจ้าหนี้ (AP) โดยดึง Vendor Bill / Credit Note
        ที่ posted และยังไม่จ่าย มาจัดกลุ่มต่อ vendor เพื่อเช็คกับใบวางบิลของ vendor
        พร้อมคอลัมน์ยอดบิล / หัก ณ ที่จ่าย / ยอดจ่ายสุทธิ
    """,
    'author': 'Autozone',
    'depends': ['base', 'account', 'mail', 'autozone_base_address', 'l10n_th_account_tax'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/vendor_payment_report_views.xml',
        'views/vendor_payment_report_menus.xml',
        'report/vendor_payment_report_report.xml',
        'report/vendor_payment_report_template.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
