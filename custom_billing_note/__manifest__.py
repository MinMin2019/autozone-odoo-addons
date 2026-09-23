{
    'name': 'Custom Billing Note',
    'version': '18.0.1.4.0',
    'category': 'Autozone/Accounting',
    'summary': 'ระบบจัดการใบวางบิลสำหรับลูกค้า (Customer Billing Note)',
    'description': """
        โมดูลสำหรับจัดทำใบวางบิล โดยดึงเอกสารใบแจ้งหนี้ (Invoices) ที่ค้างชำระมาจัดกลุ่ม
    """,
    'author': 'Autozone',
    'depends': ['base', 'account', 'mail', 'autozone_base_address', 'custom_invoice_print'],  # custom_invoice_print = ฟิลด์ x_po_reference / x_do_reference บน account.move
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/paperformat.xml',
        'views/billing_note_views.xml',
        'views/billing_note_menus.xml',
        'report/billing_note_report.xml', 
        'report/billing_note_template.xml'
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
