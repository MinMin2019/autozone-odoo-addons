{
    "name": "Growth % per Comparison Period",
    "version": "18.0.1.2.0",
    "category": "Autozone/Accounting",
    "author": "Autozone",
    "summary": "คอลัมน์ % เปลี่ยนแปลงเทียบงวดก่อนหน้า ต่อท้ายทุกงวดในรายงานการเงิน (Balance Sheet, P&L, Trial Balance ฯลฯ) "
               "แทนคอลัมน์ % เดี่ยวท้ายตารางของ Enterprise และรองรับการเปรียบเทียบมากกว่า 1 งวด "
               "(Trial Balance คิด % จากยอดเคลื่อนไหวสุทธิ Debit-Credit ของแต่ละงวด) "
               "เปิด/ปิดคอลัมน์ % ได้ที่เมนู Options ของรายงาน ค่าเริ่มต้นปิด",
    "depends": ["account_reports"],
    "data": [
        "data/trial_balance.xml",
        "data/common_size.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "custom_report_growth_percent/static/src/xml/filter_extra_options.xml",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
