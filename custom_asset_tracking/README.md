# Autozone Asset Tracking

เฟส 1a ของระบบติดตามทรัพย์สิน: **ผู้ถือครอง (Custodian) ผูกกับข้อมูลพนักงาน**

## สิ่งที่โมดูลทำ
- เพิ่มช่อง **Custodian** (`custodian_id` → `hr.employee`) บนฟอร์ม/ลิสต์สินทรัพย์
- **ซ่อนช่อง Repository** (`x_asset_repository` จาก `asset_module`) — ข้อมูลเดิมยังอยู่ใน DB ไม่ลบ
- ตัวกรอง: *No Custodian*, *Custodian Archived (Resigned)* (ของค้างกับคนลาออก) + Group by Custodian
- ลิสต์สินทรัพย์แสดงเพิ่ม: **รูป**, **Description** (`x_asset_description`), **Analytic Distribution** (v1.1.0); ซ่อนคอลัมน์ Class (Studio) เพราะซ้ำกับ Analytic (v1.2.0)
- Group by **Analytic** / **Analytic Plan** ในลิสต์ ผ่านช่องซ่อน `main_analytic_account_id` (stored) = analytic ที่ % สูงสุดใน Analytic Distribution (v1.3.0) — สินทรัพย์ที่แบ่งหลายสาขาจะอยู่กลุ่มของสาขาที่ % มากสุด
- ช่อง Custodian มี tracking ใน chatter → เห็นประวัติเปลี่ยนคนถือ

## การย้ายข้อมูลตอนติดตั้ง (post_init_hook)
เทียบชื่อใน Repository กับชื่อพนักงาน (รวมคนที่ archive) หลังตัดคำนำหน้า (นาย/นาง/นางสาว/น.ส./ว่าที่ ร.ต.) และช่องว่าง
ใส่ให้เฉพาะที่ตรงพนักงาน **คนเดียวแบบเป๊ะ** — ชื่อสะกดต่าง/หาไม่เจอปล่อยว่าง ให้บัญชีเลือกเองตามไฟล์รายชื่อ

## ยังไม่ทำ (รอเฟสถัดไป ดูดีไซน์ custom_asset_tracking)
แผนก/จุดที่ตั้ง (รอโครงแผนกนิ่ง), บังคับสาขา, ใบรับมอบ, สติกเกอร์ QR, ใบโอนย้าย, ตรวจนับ
