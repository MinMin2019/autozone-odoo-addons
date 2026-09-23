{
    "name": "Analytic Zone Auto-fill Branches",
    "version": "18.0.1.3.0",
    "category": "Autozone/Accounting",
    "author": "Autozone",
    "summary": "เลือกแผน (โซน) ในฟิลเตอร์การวิเคราะห์ของรายงานบัญชี "
               "แล้วเติม analytic account (สาขา) ในแผนนั้นเข้าช่องบัญชีให้อัตโนมัติ "
               "+ เรียงคอลัมน์สาขาตามตัวเลขนำหน้าชื่อ (natural sort)",
    "depends": ["account_reports"],
    "assets": {
        "web.assets_backend": [
            "custom_analytic_plan_autofill/static/src/js/analytic_plan_autofill.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
