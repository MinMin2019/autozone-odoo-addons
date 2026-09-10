# custom_studio_fields — สำรองฟิลด์ Studio เป็นโค้ด

สำรวจ DB **Autozone-PD** เมื่อ 2026-08-06: พบฟิลด์ `state='manual'` (สร้างนอกโมดูล) ทั้งหมด 57 ฟิลด์ + custom model 3 ตัว
โมดูลนี้เก็บเฉพาะกลุ่มที่ **Studio สร้างและใช้งานจริง** ให้อยู่ในรูปโค้ด — **ยังไม่ต้องติดตั้ง**
เก็บไว้ใช้ตอนอัพเกรดเวอร์ชัน / สร้างฐานข้อมูลใหม่ / ย้ายระบบ

## ฟิลด์ที่โมดูลนี้ครอบคลุม (Studio สร้าง, ใช้งานจริง)

| Model | Field | Type | ข้อมูลใน DB (2026-08-06) |
|---|---|---|---|
| `account.asset` | `x_studio_asset_code` (Asset Code) | char | 1,164/1,185 record — ใช้โดย `custom_asset_report_code` ด้วย |
| `account.asset` | `x_studio_location` (Location) | char | 43/1,185 record |
| `sale.order` | `x_studio_invoicing_journal` | many2one related=`journal_id` (ไม่ store) | ไม่มีคอลัมน์ใน DB (related) |

รวมทั้ง view customization ของ Studio บนฟอร์ม/ลิสต์ `account.asset` (แสดง Asset Code, แทน `x_location_id`
ของ `asset_module` ด้วย `x_studio_location`, บังคับ `account_asset_id` required)

## กลุ่มที่ *ตั้งใจไม่* ใส่ในโมดูล

### 1. ระบบสร้างเอง — ห้ามเอาไปใส่โมดูล เดี๋ยวระบบสร้างซ้ำเอง

- `x_plan2_id` … `x_plan6_id` (+ตัวลงท้าย `_1`) บน `account.analytic.line`, `budget.line`, `budget.report`, `project.project`
  รวม 40 ฟิลด์ — **Odoo สร้างอัตโนมัติจาก Analytic Plans** (plan id 2=งานบริหารส่วนกลาง, 3=ซ่อมรถยนต์,
  4=B.U. Subcontract, 5=พ่นสีชิ้นส่วนรถยนต์, 6=PDI) ตราบใดที่ plan ยังอยู่ Odoo จะสร้างฟิลด์ให้ใหม่เองเสมอ
- `x_project_task_worksheet_template_1` (model + 3 ฟิลด์) — สร้างโดยฟีเจอร์ Worksheet Template ของ
  `industry_fsm_report` (มี xmlid ของโมดูลนั้นอยู่แล้ว)

### 2. ขยะ Studio — ไม่มีข้อมูลสักแถว แนะนำให้ลบทิ้งผ่าน Studio/Technical

| Model | Field | หมายเหตุ |
|---|---|---|
| `account.move` | `x_studio_float_field_7na_1jro42a7i` ("New Decimal") | ค่า ≠ 0 อยู่ 0/38,576 |
| `account.move.line` | `x_studio_many2one_field_10l_1ju7tsh3l` ("New Many2One") | ไม่ null อยู่ 0/147,656 |
| `purchase.order` | `x_studio_one2many_field_3fi_1jtkk6kor` ("New Lines") | ชี้ model `x_purchase_order_line_63760` (0 แถว) |
| `purchase.order` | `x_studio_one2many_field_4tv_1jtkk9s2p` ("New Lines") | ชี้ model `x_purchase_order_line_f538c` (0 แถว) |

model `x_purchase_order_line_63760` / `x_purchase_order_line_f538c` (อย่างละ 3-4 ฟิลด์ + default list view)
เป็นเศษจากการทดลองกด "Add Lines" ใน Studio — ตารางว่างเปล่าทั้งคู่ ลบได้ปลอดภัย
(ลบ field one2many บน purchase.order ก่อน แล้วค่อยลบ model)

## วิธีใช้ตอนอัพเกรด/ย้ายฐาน

1. ติดตั้งโมดูลนี้ → Odoo จะรับช่วงฟิลด์ manual เดิม (`state` เปลี่ยน manual → base)
   **ข้อมูลไม่หาย** เพราะชื่อฟิลด์/คอลัมน์ตรงกันทุกตัว
2. ถ้า DB ยังมี Studio view เดิมอยู่ (`studio_customization.odoo_studio_account__0c977fae…` /
   `…cb745f41…`) ให้ปิดหรือลบ Studio view ทั้งสองก่อน ไม่งั้น Asset Code / Location โผล่ซ้ำสองที่
3. ถ้าเป็นฐานใหม่ที่ไม่เคยมีฟิลด์ → ติดตั้งได้เลย ฟิลด์+หน้าจอมาครบ

## วิธีสำรวจซ้ำในอนาคต

```sql
-- ฟิลด์ที่สร้างนอกโมดูล
SELECT model, name, ttype, relation FROM ir_model_fields WHERE state='manual' ORDER BY model, name;
-- model ที่สร้างนอกโมดูล
SELECT model, name FROM ir_model WHERE state='manual';
-- ดูว่าใครเป็นเจ้าของ (studio_customization = มาจาก Studio)
SELECT d.module, d.name, d.res_id FROM ir_model_data d
WHERE d.model='ir.model.fields' AND d.res_id IN (SELECT id FROM ir_model_fields WHERE state='manual');
```
