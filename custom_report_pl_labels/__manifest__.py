{
    "name": "P&L Thai/English Labels",
    "version": "18.0.1.2.0",
    "category": "Autozone/Accounting",
    "author": "Autozone",
    "summary": "ตั้งชื่อบรรทัดในรายงาน Profit and Loss ใหม่ทั้งภาษาอังกฤษและไทย ตามแบบงบกำไรขาดทุนที่ใช้ในไทย "
               "(ตัดคำ Less/Plus ออกจากชื่อหัวข้อ) + แบ่งค่าใช้จ่ายในการขาย (611) / บริหาร (หมวด 6 ที่เหลือ) "
               "และแยกต้นทุนทางการเงิน (81x) กับภาษีเงินได้ (821x) ไว้ท้ายงบ — กำไรสุทธิยอดเท่าเดิม",
    "depends": [
        "account_reports",
        "custom_report_pl_cost_groups",
        "custom_report_ebda",
    ],
    "data": [
        "data/profit_and_loss_structure.xml",
        "data/apply_labels.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
