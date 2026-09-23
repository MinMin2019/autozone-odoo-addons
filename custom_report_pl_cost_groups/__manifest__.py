{
    "name": "P&L Cost of Revenue Groups",
    "version": "18.0.1.0.0",
    "category": "Autozone/Accounting",
    "author": "Autozone",
    "summary": "แบ่ง Less Costs of Revenue ในรายงาน Profit and Loss เป็นกลุ่มย่อยตามช่วงรหัสบัญชี "
               "(ค่าแรงงานทางตรง 511 / ค่าสวัสดิการอื่น 512 / ค่าอะไหล่ 52 / ค่าสี 531 / "
               "ค่าวัสดุสิ้นเปลืองโรงงาน 532 / ค่าใช้จ่ายผลิตอื่น 54-55) พร้อมยอดรวมย่อยแต่ละกลุ่ม "
               "ตามรูปแบบที่ฝ่ายบัญชีกำหนด — ยอดรวม Less Costs of Revenue ยังนับทุกบัญชีประเภท "
               "Cost of Revenue เหมือนเดิม บัญชีที่รหัสไม่เข้าช่วงจะไปอยู่กลุ่ม 'ต้นทุนอื่น' (ซ่อนเมื่อเป็น 0)",
    "depends": ["account_reports"],
    "data": [
        "data/profit_and_loss_cost_groups.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
