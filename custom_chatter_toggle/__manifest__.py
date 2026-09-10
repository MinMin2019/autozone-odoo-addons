# -*- coding: utf-8 -*-
{
    "name": "Custom Chatter Toggle",
    'author': 'Autozone',
    'category': 'Autozone/Tools',
    "version": "18.0.1.2.0",
    "summary": "3-state view toggle on form views: show all / hide PDF preview / hide preview + chatter",
    "depends": ["web", "mail"],
    "assets": {
        "web.assets_backend": [
            "custom_chatter_toggle/static/src/js/chatter_toggle.js",
            "custom_chatter_toggle/static/src/scss/chatter_toggle.scss",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}