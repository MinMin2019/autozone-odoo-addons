# custom_report_pl_labels — งบกำไรขาดทุน ไทย/อังกฤษ

ตั้งชื่อบรรทัดในรายงาน **Profit and Loss** ใหม่ทั้ง 2 ภาษา ตามแบบงบกำไรขาดทุนที่ใช้ในไทย และจัดโครงตามที่ฝ่ายบัญชีกำหนด
ผู้ใช้ที่ตั้งภาษาไทยจะเห็นชื่อไทย ผู้ใช้ภาษาอังกฤษเห็นชื่ออังกฤษ **กำไรสุทธิยอดเท่าเดิม**

ทำไมต้องทำ: ชื่อมาตรฐานของ Odoo มีคำ "Less/Plus" ในหัวข้อ พอ Odoo เติม "Total" หน้าชื่อเอง
จึงได้ "Total Less Costs of Revenue" ซึ่งไม่ใช่แบบที่ใช้ในงบการเงิน และคำแปลไทยของ Odoo ก็ผิดความหมาย

## โครงงบ (v1.2.0, 17 พ.ย. 2026 — EBDA เปลี่ยนชื่อเป็น EBITDA เพราะไม่ได้หักดอกเบี้ยจ่าย)

| บรรทัด | อังกฤษ | ไทย | บัญชี |
|---|---|---|---|
| REV | Revenue | รายได้ | ประเภท Income |
| COS | Cost of Sales and Services | ต้นทุนขายและบริการ | ประเภท Cost of Revenue (กลุ่มย่อยจาก custom_report_pl_cost_groups) |
| GRP | Gross Profit | กำไรขั้นต้น | |
| EXP | Selling and Administrative Expenses | ค่าใช้จ่ายในการขายและบริหาร | ประเภท Expense ยกเว้น 81x / 821x |
| ├ AZ_EXP_SELL | Selling Expenses | ค่าใช้จ่ายในการขาย | 611xxx |
| ├ AZ_EXP_ADMIN | Administrative Expenses | ค่าใช้จ่ายในการบริหาร | หมวด 6 ที่เหลือ |
| └ AZ_EXP_MISC | Other Expenses (Unmapped Account Codes) | ค่าใช้จ่ายอื่น (รหัสนอกช่วง) | Expense นอกหมวด 6 (เช่น 821003, 999xxx) ซ่อนเมื่อ 0 |
| INC | Operating Profit (Loss) | กำไร (ขาดทุน) จากการดำเนินงาน | |
| OIN | Other Income | รายได้อื่น | ประเภท Other Income |
| AZ_EBDA | Earnings before Interest, Tax, Depreciation and Amortization (EBITDA) | กำไรก่อนดอกเบี้ย ภาษีเงินได้ ค่าเสื่อมราคาและรายการตัดบัญชี (EBITDA) | INC + OIN |
| OEXP | Depreciation and Amortization | ค่าเสื่อมราคาและค่าตัดจำหน่าย | ประเภท Depreciation |
| AZ_FIN | Finance Costs | ต้นทุนทางการเงิน | Expense 81xxx (ดอกเบี้ยจ่าย) |
| AZ_EBT | Net Profit (Loss) before Income Tax | กำไร (ขาดทุน) สุทธิก่อนภาษีเงินได้ | EBDA − OEXP − FIN |
| AZ_TAX | Income Tax Expense | ค่าใช้จ่ายภาษีเงินได้ | Expense 821xxx ยกเว้น 821003 (ภาษีธุรกิจเฉพาะ) |
| NEP | Net Profit (Loss) | กำไร (ขาดทุน) สุทธิ | EBT − TAX |

กลุ่มย่อยต้นทุน: Direct Labor / ค่าแรงงานทางตรง, Employee Benefits / ค่าสวัสดิการพนักงาน, Spare Parts / ค่าอะไหล่,
Paint / ค่าสี, Factory Supplies / ค่าวัสดุสิ้นเปลืองโรงงาน, Other Production Overhead / ค่าใช้จ่ายผลิตอื่น,
Other Costs (Unmapped Account Codes) / ต้นทุนอื่น (รหัสนอกช่วง)

## กลไก
- `data/profit_and_loss_structure.xml`: ถอด groupby ของ EXP, แก้ domain EXP ให้ไม่รวม 81x/821x, เพิ่มบรรทัดลูก/ท้ายงบ,
  แก้สูตร NEP เป็น `AZ_EBT - AZ_TAX` (คณิตเท่าสูตรเดิมของ Odoo)
- `data/apply_labels.xml` เรียก `account.report.line._az_apply_pl_labels()` ทุกครั้งที่ติดตั้ง/อัปเกรด
  เขียนชื่อด้วย `update_field_translations` (en_US + th_TH ถ้าเปิดภาษาไทยไว้)
- depends `custom_report_pl_cost_groups` + `custom_report_ebda` — ถ้าอัปเกรด account_reports หรือ 2 โมดูลนั้น
  (ซึ่ง reset ชื่อ/สูตรกลับ) Odoo จะอัปเกรดโมดูลนี้ตามและเขียนทับให้เอง
- แก้ชื่อ: แก้ dict ใน `models/account_report_line.py` แล้ว bump version + Upgrade
- deploy: `D:\odoo18\scripts\pl_labels\deploy_dev.cmd` / `deploy_prod.cmd` (เช็กกำไรสุทธิไม่เปลี่ยน + แสดงบัญชีในบรรทัดใหม่)
- ถอนโมดูล: ชื่อ/สูตรจะค้าง จนกว่าจะ Upgrade account_reports (ได้ของ Odoo คืน)
