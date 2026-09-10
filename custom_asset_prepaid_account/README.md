# Autozone Asset Prepaid Account

เปิดให้เลือกบัญชีประเภท **Prepayments (ค่าใช้จ่ายจ่ายล่วงหน้า)** ในฟอร์มสินทรัพย์ได้

## ปัญหาที่แก้

บัญชี `152103 ค่าใช้จ่ายจ่ายล่วงหน้าอื่นๆ` ไม่โผล่ในดรอปดาวน์ช่อง Depreciation Account
บนฟอร์มสินทรัพย์ ทั้งที่บัญชีมีอยู่จริง ไม่ได้ deprecated และอยู่บริษัทเดียวกัน

สาเหตุอยู่ที่ตัว view ของ Odoo เอง (`account_asset/views/account_asset_views.xml`)
ที่ระบุ `domain` ไว้บนช่องบัญชีโดยตรง — domain บน view ทับ domain ที่ประกาศในไฟล์ Python

| ช่อง | ประเภทบัญชีที่ Odoo ยอมให้เลือก |
|---|---|
| Fixed Asset Account | `asset_fixed`, `asset_non_current`, `asset_current` |
| Depreciation Account | `asset_fixed`, `asset_non_current`, `asset_current` |
| Expense Account | `expense_depreciation`, `expense` |

`asset_prepayments` ไม่อยู่ในลิสต์ บัญชีเลยหายไปจากดรอปดาวน์แบบเงียบ ๆ พิมพ์ค้นก็ไม่เจอ

ใน Autozone-PD มีบัญชีประเภทนี้ 3 ตัว: `152101` / `152102` / `152103`

## สิ่งที่โมดูลทำ

เพิ่ม `asset_prepayments` เข้า domain ของ **Fixed Asset Account** และ **Depreciation Account**
ทั้ง 2 ชุดในฟอร์ม (ฟอร์มสินทรัพย์ปกติ + ฟอร์ม Asset Model)

**ไม่ทำ:**
- ไม่แก้ผังบัญชี ไม่เปลี่ยน account_type ของบัญชีใด ๆ → งบดุลเหมือนเดิมทุกบรรทัด
  (บัญชียังรวมอยู่ใต้หัวข้อย่อย *Prepayments* ของ *สินทรัพย์หมุนเวียน*)
- ไม่แตะ **Expense Account** โดยตั้งใจ — ปลายทางของการทยอยตัดค่าใช้จ่ายล่วงหน้า
  ต้องลงบัญชีค่าใช้จ่ายในงบกำไรขาดทุน (`expense`) อยู่แล้ว

## หมายเหตุการทำ xpath

`account_asset.view_account_asset_form` ประกาศกลุ่ม `Accounting` ไว้ **2 ชุด** ในไฟล์เดียว
ชุดแรกคือฟอร์ม Asset Model (`<group invisible="state != 'model'">`) ชุดที่สองคือฟอร์ม
สินทรัพย์ปกติ (อยู่ใน `<page name="main_page">`) — xpath ของ Odoo หยิบเฉพาะ node แรก
ที่ match จึงต้องเขียนแยกทั้ง 2 ชุด ห้ามใช้ `//field[@name='...']` เฉย ๆ

ระวังเพิ่ม: `//field[@name='account_asset_id']` ยังไปโดน field invisible ที่ประกาศไว้
บนสุดของ sheet ด้วย (`<field name="account_asset_id" invisible="1"/>`) ซึ่งไม่มี domain

## เกี่ยวข้องกับ

- `custom_studio_fields` — inherit view เดียวกัน (คนละ xpath ไม่ชนกัน)
- `custom_asset_report_code`, `custom_asset_report_class`
