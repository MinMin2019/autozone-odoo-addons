{
    "name": "Analytic Filter Tags: Branch Code Only",
    "version": "18.0.1.1.0",
    "category": "Autozone/Accounting",
    "author": "Autozone",
    "summary": "ชิป analytic ในฟิลเตอร์รายงานบัญชี + หัวคอลัมน์ slice รายสาขา "
               "แสดงเฉพาะตัวย่อสาขา เช่น BPH แทน ฮอนด้า บางปู",
    "depends": ["account_reports"],
    "assets": {
        "web.assets_backend": [
            "custom_analytic_code_tags/static/src/js/analytic_code_tags.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
