# -*- coding: utf-8 -*-
{
    'name': "Custom Asset Module",
    'summary': "Add image and extra fields (Description, Barcode) to Asset form.",
    'author': 'Autozone',
    'website': "https://www.autozonegroup.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Autozone/Accounting',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'web', 'account_asset'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'asset_module/static/src/js/image_preview.js',
        ],
    },
}

