{
    "name": "Growth % per Comparison Period",
    "version": "18.0.1.1.0",
    "category": "Autozone/Accounting",
    "author": "Autozone",
    "summary": "คอลัมน์ % เปลี่ยนแปลงเทียบงวดก่อนหน้า ต่อท้ายทุกงวดในรายงานการเงิน (Balance Sheet, P&L, Trial Balance ฯลฯ) "
               "แทนคอลัมน์ % เดี่ยวท้ายตารางของ Enterprise และรองรับการเปรียบเทียบมากกว่า 1 งวด "
               "(Trial Balance คิด % จากยอดเคลื่อนไหวสุทธิ Debit-Credit ของแต่ละงวด)",
    "depends": ["account_reports"],
    "data": [
        "data/trial_balance.xml",
        "data/common_size.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
