# คู่มือระบบเงินเดือน Odoo 18 — ฉบับสมบูรณ์
### ติดตั้ง · รันสคริปต์ · ใช้งานประจำเดือน · แก้ปัญหา

> อัปเดต: 27 ส.ค. 2026 | โมดูล `import_payslip_inputs` ≥ 18.0.3.0.0 | DB: Autozone-PD
> ทุกคำสั่งรันจากโฟลเดอร์ `D:\odoo18` | สคริปต์ทั้งหมดอยู่ `custom_addons/import_payslip_inputs/tools/`

---

## 0. กฎเหล็ก 3 ข้อ (อ่านก่อนทำอะไรทั้งสิ้น)

1. **Restore DB ใหม่เมื่อไหร่ → ต้องรัน `wire_payroll_accounts_shell.py` ซ้ำเสมอ**
   โครงสร้าง/rules มากับโมดูล แต่การผูกเลขบัญชี+สมุดเงินเดือน+โหมดรวมใบสำคัญเป็น "สถานะใน DB"
   หายไปกับการ restore ทุกครั้ง — อาการถ้าลืม: ยืนยันสลิปแล้ว**ใบสำคัญว่างเปล่า** แยกหลายใบ ลงสมุด "Salaries"
   (เจอมาแล้วจริง 27 ส.ค. 2026)
2. **ทำอะไรเสร็จ ให้รัน `smoke_test_shell.py` ปิดท้ายเสมอ** — ปลอดภัย 100% (rollback ตัวเอง)
   ถ้าขึ้น "ผ่าน" = ทั้งสายพร้อมใช้ ถ้า "ไม่ผ่าน" = มีขั้นตอนตกหล่น อย่าปล่อยผ่านไปงวดจริง
3. **ทุกอย่างรันซ้ำได้ (idempotent)** — import ซ้ำ = อัปเดตคนเดิมด้วย External ID ไม่สร้างซ้ำ
   สงสัยเมื่อไหร่รันใหม่ได้เลย ไม่ต้องกลัวข้อมูลเบิ้ล

---

## 1. ภาพรวมระบบ

**หลักการเฟส 1 (โมเดล A)**: ระบบเงินเดือนเดิมยังเป็นเครื่องคิดเลข — ทุกยอดรายได้/รายการหัก
มากับไฟล์ Excel รายเดือน, Odoo ทำหน้าที่ออกสลิป + ตั้งใบสำคัญบัญชีอัตโนมัติ (ร่างเสมอ บัญชีเป็นคน Post)

```
ไฟล์ HR (รายชื่อ/ผัง)             ไฟล์ payroll รายเดือน
      │ convert_employees.py            │ HR อัปโหลดผ่านหน้าเว็บ (wizard)
      ▼                                 ▼
  data/ready3/*.xlsx  ──import──▶  Odoo: พนักงาน+ผัง+สัญญา ──▶ Batch ──▶ สลิป ──▶ ใบสำคัญ (ร่าง)
                                                                              │ บัญชีตรวจ + Post
                                                                              ▼
                                                    สมุดรายวันเงินเดือน (PAYR) 1 ใบ/งวด ยอดรวมรายบัญชี
```

**โครงสร้างเงินเดือน 3 ชุดตามกลุ่มสายงาน** (บัญชี Dr ต่างกัน):
| กลุ่มสายงานในไฟล์ HR | Structure | บัญชีเงินเดือน |
|---|---|---|
| ผลิต-บริการ, ผลิต-ชิ้นส่วน | เงินเดือน - โรงงาน | 511xxx |
| สำนักงาน | เงินเดือน - สำนักงาน | 621001, 62xxxx |
| บริหาร | เงินเดือน - ผู้บริหาร | 621000 |

**การตัดสินใจที่ล็อกไว้แล้ว**: ทุกสถานะว่าจ้าง (รวมจ่ายนอกระบบ 16 + SRT 14) มีสัญญา+สลิป เพื่อให้ต้นทุนเข้าบัญชีครบ /
สัญญาจ้างใช้ wage=0 ได้ (ยอดจริงมากับไฟล์) / เงินกู้มาจากโมดูล `custom_hr_loan` — **ห้าม**มีรายการ LOAN ในไฟล์ payroll
(wizard บล็อกให้อัตโนมัติ) / ใบสำคัญรวม 1 ใบ/งวด ไม่โชว์เงินเดือนรายคนใน GL

---

## 2. สารบัญสคริปต์ (ทั้งหมดอยู่ใน `tools/`)

วิธีรันมี 2 แบบ — **แบบ python ปกติ** กับ **แบบ odoo shell** (สคริปต์ที่ลงท้าย `_shell.py`):
```bash
# แบบ python ปกติ (แปลงไฟล์ ไม่แตะ DB)
PYTHONUTF8=1 python custom_addons/import_payslip_inputs/tools/<ชื่อสคริปต์>.py
# แบบ odoo shell (แตะ DB - แทน <DB> ด้วยชื่อฐาน เช่น Autozone-PD)
PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <DB> --no-http < custom_addons/import_payslip_inputs/tools/<ชื่อสคริปต์>.py
```

| สคริปต์ | แบบ | ทำอะไร | รันเมื่อไหร่ |
|---|---|---|---|
| `convert_employees.py` | python | แปลงไฟล์ HR (2 ชีต) → ชุด import ใน `data/ready3/` + FIX_REPORT | HR ส่งไฟล์รายชื่อใหม่ทุกครั้ง |
| `prepare_db_shell.py` | shell | ลบ employee ที่เกิดจากการสร้าง user, ลบ field Studio, archive Administrator | ครั้งแรกของ DB ใหม่/restore เท่านั้น |
| `import_all_shell.py` | shell | import แผนก→สาขา→พนักงาน→หัวหน้า→ผูก user (commit เมื่อ error=0 เท่านั้น) | หลัง convert ทุกครั้ง |
| `gen_payroll_config.py` | python | ตารางแม็ป Business Plus → Odoo (1 รหัส = 1 บรรทัดสลิป) → generate XML structure/rules + wire script + `bplus_map.json` + `doc/BPLUS_CODE_MAP.md` | เมื่อเพิ่ม/แก้รายได้-รายหัก หรือเปลี่ยนบัญชี (แล้ว -u + wiring) |
| `wire_payroll_accounts_shell.py` | shell | ผูกบัญชี Dr/Cr + ชื่อ/รหัส/ลำดับ 186 rules + สร้างสมุด PAYR + เปิดโหมดรวมใบ + เก็บกวาดของเก่า | **ทุกครั้งหลัง restore DB** + **ทุกครั้งหลัง -u โมดูล** (record ใน XML เป็น noupdate) |
| `create_bplus_reader_login.sql` / `change_bplus_reader_password.sql` | SQL (SSMS, sa) | สร้าง login อ่านอย่างเดียว odoo_reader / เปลี่ยนรหัสผ่าน (แล้วอัปเดต System Parameter bplus.password + ini) | ครั้งแรก / เมื่อต้องการหมุนรหัส |
| `bplus_extract.py` | python (เครื่องในออฟฟิศ) | ดึงผลคำนวณงวดจาก SQL Server ของ Business Plus → ไฟล์ `payslip_inputs_<ปี>-<เดือน>.xlsx` พร้อมชีต Control ไว้เทียบยอดสุทธิ | ทุกเดือนหลัง HR ปิดงวดใน Business Plus |
| `create_contracts_shell.py` | shell | สร้างสัญญาจ้าง Running ตามกลุ่มสายงาน (wage จากไฟล์ 04 ถ้ามี ไม่มีก็ 0) / รันซ้ำ = อัปเดตเงินเดือน | หลัง import พนักงาน และตอน HR ส่งเงินเดือนจริงมาเติม |
| `set_contract_analytic_shell.py` | shell | ผูกกอง Analytic รายสาขาลงสัญญาทุกใบ (จับคู่รหัสสาขา = code ของกอง, AZG→H.O.) | หลังสร้างสัญญา + เมื่อมีพนักงาน/สาขาใหม่ + หลัง restore |
| `smoke_test_shell.py` | shell | ทดสอบทั้งสาย สลิป→ใบสำคัญ แล้ว rollback ตัวเอง (ปลอดภัย 100%) | ปิดท้ายทุกงานติดตั้ง/ก่อนเปิดงวดจริง |

สคริปต์ฝั่ง converter อ่านไฟล์ต้นทางจาก path ที่กำหนดไว้บนหัวสคริปต์ (`SRC = ...`) —
HR ส่งไฟล์ใหม่ให้วางทับ path เดิม หรือแก้ `SRC` ให้ชี้ไฟล์ใหม่

---

## 3. ติดตั้งจากศูนย์ / หลัง Restore DB (ทำตามลำดับ ห้ามสลับ)

> ใช้ชุดนี้ทั้งตอนขึ้นเครื่องใหม่, restore production มาใหม่, และวัน deploy จริง

```bash
cd D:\odoo18

# (1) ติดตั้ง/อัปเกรดโมดูล — ดึง hr_payroll + hr_payroll_account + โครงสร้างทั้งหมดมาให้
PYTHONUTF8=1 python odoo-bin -c odoo.conf -d <DB> -i import_payslip_inputs --stop-after-init
#   ถ้าติดตั้งอยู่แล้ว ใช้ -u แทน -i

# (2) ล้างของเก่าใน DB (เฉพาะครั้งแรกของ DB นั้น - มีตัวกันพลาดถ้ารันซ้ำ)
PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <DB> --no-http < custom_addons/import_payslip_inputs/tools/prepare_db_shell.py

# (3) ผูกบัญชี+สมุด+โหมดรวมใบ  ★ กฎเหล็กข้อ 1 - ห้ามข้ามเด็ดขาด ★
PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <DB> --no-http < custom_addons/import_payslip_inputs/tools/wire_payroll_accounts_shell.py
#   ต้องเห็น: "ผูกบัญชีแล้ว 186 rules | หาไม่เจอ 0" และ "ยังไม่ผูกบัญชี ... []" ทั้ง 3 บรรทัด

# (4) แปลงไฟล์ HR (ถ้ามีไฟล์ใหม่ / ข้ามได้ถ้า data/ready3 เป็นชุดล่าสุดอยู่แล้ว)
PYTHONUTF8=1 python custom_addons/import_payslip_inputs/tools/convert_employees.py

# (5) นำเข้าพนักงานทั้งชุด
PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <DB> --no-http < custom_addons/import_payslip_inputs/tools/import_all_shell.py
#   ต้องเห็น: error 0 ทุกไฟล์ + "=== COMMITTED ===" + ยอดผังเหลือคนเดียว (กรรมการผู้จัดการ)

# (6) สร้างสัญญาจ้าง
PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <DB> --no-http < custom_addons/import_payslip_inputs/tools/create_contracts_shell.py

# (6b) ผูกกอง Analytic รายสาขาลงสัญญา (ต้นทุนรายสาขา)
PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <DB> --no-http < custom_addons/import_payslip_inputs/tools/set_contract_analytic_shell.py
#   ต้องเห็น: "จับคู่ครบทุกสัญญา ไม่มีตกหล่น"

# (7) สโมคเทสต์  ★ กฎเหล็กข้อ 2 ★
PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <DB> --no-http < custom_addons/import_payslip_inputs/tools/smoke_test_shell.py
#   ต้องเห็น: "***** ผลทดสอบ: ผ่าน *****"

# (8) restart service Odoo หนึ่งครั้ง แล้วตรวจใน UI ตามเช็คลิสต์ข้างล่าง
```

**เช็คลิสต์ตรวจใน UI หลังติดตั้ง**
- [ ] Employees: จำนวน active = คนในไฟล์ + เก้าอี้รักษาการ (ปัจจุบัน 445+3=448)
- [ ] Org Chart: ยอดผังคนเดียว (กรรมการผู้จัดการ) กางได้ทุกชั้น มีกล่องเก้าอี้รักษาการ
- [ ] สุ่มพนักงาน: คำนำหน้า, Tag กลุ่มสายงาน+สถานะว่าจ้าง, Job Level, แผนก 4 ชั้น, สาขา
- [ ] Contracts: Running = จำนวนพนักงานจริง (445), Structure Type ถูกกลุ่ม
- [ ] Payroll → Configuration → Structures: 3 ชุด Legacy Import แต่ละ rule มีบัญชี Dr/Cr
- [ ] คนมี login: Related User ผูกอยู่ (17 คน)
- [ ] ไล่ `data/ready3/FIX_REPORT.xlsx` ให้ HR ตามเก็บ

---

## 3ก. การรันบน Production (server Windows ผ่าน SSH)

Production ไม่มี path `D:\odoo18` — ใช้ตัวรันที่ติดตั้งไว้แล้วที่ `C:\Users\Administrator\run_payroll_tool.cmd`
ซึ่งชี้ไปโฟลเดอร์ tools ของโมดูลบน server ให้เอง:

```bash
# รันสคริปต์ตัวไหนก็ได้ในโฟลเดอร์ tools (ชื่อไฟล์อย่างเดียว)
ssh administrator@103.253.74.190 "cmd /c C:\Users\Administrator\run_payroll_tool.cmd wire_payroll_accounts_shell.py"
```

- ตัว .cmd ตั้ง `chcp 65001` + `PYTHONUTF8=1` ให้แล้ว (ไม่งั้น shell พังด้วย UnicodeEncodeError จากภาษาไทย)
- สคริปต์ shell ทุกตัว**หา path ของโมดูลเอง** (ผ่าน `get_module_path`) จึงใช้ไฟล์ `data/ready3` บน server ได้ทันที
- **อัปเดตโค้ด/ข้อมูลขึ้น server**: scp ไป `C:/Users/Administrator/` ก่อน แล้ว `Copy-Item` เข้าโฟลเดอร์โมดูล
  (scp ตรงเข้า `C:\Program Files\...` ไม่ได้เพราะช่องว่างในชื่อ path)
- Odoo path บน prod: `C:\Program Files\Odoo 18.0.20260105` · DB `Autozone-PD` · service `odoo-server-18.0`

**ลำดับ deploy จริง (ทำแล้ว 28 ส.ค. 2026)**: copy โมดูล 2 ตัว (`import_payslip_inputs`, `custom_hr_loan`)
→ ติดตั้ง `-i` → prepare_db → wiring → import_all → create_contracts → set_contract_analytic → smoke_test
— ทำได้ขณะ service รันอยู่ ไม่ต้อง restart (registry signal ทำงานเอง)

> ก่อนแตะ production ทุกครั้ง: ตรวจว่ามี backup ล่าสุด (task "Odoo DB Backup" 01:00 → `D:\OdooBackups`)
> และสำรวจ employee เดิมก่อนล้างเสมอ — บน production ต้องเช็คว่ามีข้อมูลอื่นผูกอยู่ไหม (ใบลา/ค่าใช้จ่าย/timesheet)

---

## 4. เมื่อ HR ส่งไฟล์รายชื่อ/ข้อมูลใหม่ (รอบอัปเดต)

1. วางไฟล์ใหม่แล้วตรวจว่า `SRC` หัวสคริปต์ `convert_employees.py` ชี้ถูกไฟล์
   (รูปแบบไฟล์ HR ที่รองรับ: ชีตผัง "P'หมูอัพเดท" + ชีตข้อมูลส่วนตัว "Data Odoo(ต้องเพิ่ม)")
2. รันข้อ (4) → (5) จากหัวข้อ 3 — จบ (คนเดิมถูกอัปเดต คนใหม่ถูกสร้าง)
3. คนที่**หายไปจากไฟล์** จะ**ไม่ถูกลบอัตโนมัติ** (กันลบคนมีสลิปโดยพลาด) → ลาออกจริงให้ archive รายคนใน UI
4. ถ้ามีพนักงานใหม่ → รันข้อ (6) ซ้ำ เพื่อสร้างสัญญาให้คนที่ยังไม่มี
5. สิ่งที่ converter จัดการเองอัตโนมัติ (อย่าไปทำมือ): แยกคำนำหน้าออกจากชื่อ, เติม marital=single,
   แปลง พ.ศ.→ค.ศ., จังหวัดไทย→รหัสระบบ (พร้อมแก้คำสะกดผิด), เติม 0 หน้าเบอร์โทร, เลขบัตรผิดรูป→ว่าง+รายงาน,
   **แถวรหัสซ้ำในชีตผัง = เก้าอี้รักษาการ** (สร้างกล่องเงา + จัดทีมให้อัตโนมัติ), กันเลข 0 หน้ารหัสหาย

**เก้าอี้รักษาการ (กติกาไฟล์ HR)**: คนควบตำแหน่งให้มี 2 แถวในชีตผัง — แถวหลัก (OnHand 1)
+ แถวเก้าอี้ (OnHand 0, ตำแหน่งวงเล็บ "(รักษาการ...)", กรอกฝ่าย/แผนกของเก้าอี้) →
ระบบสร้างกล่องเงา ไม่มีสัญญา/ไม่เข้า payroll, ทีมในฝ่ายเดียวกับเก้าอี้ถูกโยงเข้าเก้าอี้เอง
ได้คนจริงมานั่ง: เปลี่ยนชื่อกล่อง+ใส่รหัส/user/สัญญาของคนใหม่ ทีมไม่ต้องย้าย

---

## 5. งานประจำเดือน (โฟลว์ผู้ใช้)

### ฝั่ง HR
0. **ทางหลัก: ปุ่มใน Odoo** — หลัง Generate Payslips (ข้อ 2) กด **Import Inputs (Excel)** → เลือก "ดึงจาก Business Plus"
   ระบบเติมปี/เดือนให้จากวันสิ้นงวดของ Batch → กด **ดึงจาก Business Plus (Preview)** → ได้หน้า Preview ทันที (ข้ามข้อ 0ข และ 3)
   ต้องตั้งค่าครั้งเดียว: Settings › Technical › **System Parameters** 4 ค่า `bplus.server` (IP Tailscale ของเครื่อง SQL Server บน production
   / 192.168.100.5 บนเครื่องใน LAN), `bplus.database` = PayrollAutozone, `bplus.user` = odoo_reader, `bplus.password`
   (+ `bplus.driver` ถ้าต้องระบุ เช่น `ODBC Driver 17 for SQL Server`) และ server Odoo ต้องมี **ODBC Driver 17/18 for SQL Server + pyodbc**
   (`<python ของ Odoo> -m pip install pyodbc` แล้ว restart service) — ถ้ายังไม่ได้ตั้ง หน้าจอจะขึ้นเตือนสีแดง
0ข. **ทางสำรอง: สคริปต์** (เครื่องในออฟฟิศที่มองเห็น 192.168.100.5 — ทำหลังปิดงวดใน Business Plus แล้ว):
   ```
   PYTHONUTF8=1 python bplus_extract.py --year 2026 --month 9 --out D:\payroll
   ```
   ครั้งแรกต้องมีไฟล์ `%USERPROFILE%\bplus_extract.ini` (server/database/user/password — ใช้ login อ่านอย่างเดียว
   `odoo_reader` สร้างด้วย `tools/create_bplus_reader_login.sql`) และวาง `bplus_map.json` ไว้ข้างสคริปต์
   - สคริปต์บอกชื่อ Batch + ช่วงวันที่ให้ (งวด 22 → 21 จ่าย 30) และ**ตรวจสมการ รายได้ − หัก − เงินกู้ = สุทธิ BPlus ทุกคน**ก่อนสร้างไฟล์
   - ถ้าหยุดพร้อมข้อความ "รหัส Business Plus ที่มียอดเงินแต่ไม่อยู่ในตาราง map" → HR เพิ่มรหัสใหม่ใน Business Plus
     ต้องเพิ่มในตาราง `gen_payroll_config.py` ก่อน (หัวข้อ 6) ห้ามข้าม
   - ไฟล์ที่ได้มี 4 ชีต: Import (wizard อ่าน) / Control (ยอดต่อคนไว้เทียบ) / Info / Skipped (รหัสที่ไม่นำเข้า เช่น สถิติวันลา, เงินกู้)
1. Payroll → Payslips → **Batches → New** ตั้งชื่อ+ช่วงวันที่ตามที่สคริปต์บอก เช่น "เงินเดือน ก.ย. 2569" 22 ส.ค. → 21 ก.ย.
2. กด **Generate Payslips** → เลือก Structure ทีละกลุ่ม (โรงงาน → สำนักงาน → ผู้บริหาร รัน 3 รอบใน Batch เดียว)
   ระบบสร้างสลิปให้ทุกคนที่มีสัญญา Running
3. (เฉพาะทางสำรอง) กด **Import Inputs (Excel)** → เลือก "อัปโหลดไฟล์ Excel" → อัปโหลดไฟล์จากข้อ 0ข
   - ทั้งสองทาง: พนักงานที่มีใน Business Plus แต่ยังไม่มีใน Odoo → ระบบฟ้องเป็นรายชื่อ (ไม่นำเข้าอะไรเลย) → HR สร้างพนักงาน+สัญญาก่อน (คู่มือ Employee_Lifecycle) แล้ว Generate Payslips + ดึงใหม่
   - ช่วงวันที่ Batch ไม่ตรงงวด Business Plus (22 → 21) → เตือนในช่อง "คำเตือน" ไม่บล็อก แต่ควรแก้ Batch ให้ตรงก่อนปิดงวด
   - ชื่อสะกดต่างกันสองระบบ → แค่**เตือน** (นำเข้าตามรหัส) รายชื่ออยู่ในช่อง "คำเตือน" และแชทเตอร์ → แจ้ง HR แก้การสะกดให้ตรง
   - ไฟล์ทำมือ (ไม่มีชีต Control) ยังใช้ได้ตามกติกาเดิม: จับคู่ด้วย**รหัสพนักงาน** / จำนวนเงิน**ค่าบวกเสมอ** / ห้ามมี LOAN
   - Import ซ้ำ = ล้างของเก่าที่มาจากไฟล์แล้วลงใหม่ทั้งชุด (ไฟล์คือความจริง รายการคีย์มือไม่ถูกแตะ)
4. หน้า **Preview**: ระบบตรวจแล้วว่ายอดในไฟล์ตรงกับสุทธิ Business Plus ทุกคน (ถ้าไม่ตรงจะไม่ให้ไปต่อ) → กด **ยืนยันนำเข้า**
5. หน้า **ผลเทียบ NET**: ระบบเทียบ NET ของสลิปแต่ละใบกับสุทธิ Business Plus
   - "ตรง" = จบ · "ต่างเท่ากับเงินกู้" = ปกติ ไปทำข้อ 6 · "ไม่ตรง" = ห้ามปิดงวด ตรวจสลิปคนนั้นก่อน (ผลถูกบันทึกในแชทเตอร์ของ Batch)
6. **เงินกู้** — ในหน้า Import เลือก "เงินกู้หักจาก" ได้ 2 แบบ (ค่าเริ่มต้น = ทะเบียน; ตั้งค่าเริ่มต้นถาวรได้ที่ System Parameter `bplus.loan_source` = `module` หรือ `bplus`):
   - **ทะเบียนเงินกู้ใน Odoo หักเอง** (แนะนำเมื่อทะเบียนครบ): ยอด 2320 ของ Business Plus ไม่ถูกนำเข้า → หลัง Preview/ยืนยัน กด **หักเงินกู้พนักงาน** บน Batch → คนที่ "ต่างเท่ากับเงินกู้" ต้องกลายเป็นตรง
   - **หักตามยอด Business Plus**: นำเข้า 2320 เป็นรายการ LOAN ตามยอดเดิม ทะเบียนเงินกู้ใช้ดู/เทียบเท่านั้น **ห้ามกด "หักเงินกู้พนักงาน" ซ้ำ** (ระบบกันหักซ้ำอยู่แล้ว แต่จะขึ้นเตือนทุกคน)
   - ทั้งสองแบบ หน้า Preview มีตาราง **ตรวจเงินกู้**: เทียบยอด 2320 ของ Business Plus กับงวดที่ถึงกำหนด (date_due ≤ วันสิ้นงวด Batch, ยังไม่ชำระเอง) ในทะเบียน แยกเป็น ตรง / ยอดต่าง / BPlus หักแต่ทะเบียนไม่มีงวด / ทะเบียนมีงวดแต่ BPlus ไม่หัก — **เตือน ไม่บล็อก** และบันทึกลงแชทเตอร์ตอนยืนยัน → ส่งรายชื่อให้ HR/บัญชีตามแก้ทะเบียนหรือ Business Plus ให้ตรงกัน
7. สุ่มตรวจสลิป (ทุกรายการแยกบรรทัดตามรหัส Business Plus รวม OT 4 อัตรา) → **Confirm** ทั้ง Batch → ระบบตั้งใบสำคัญร่างให้บัญชี

### ฝั่งบัญชี
8. เปิดใบสำคัญร่างในสมุดรายวันเงินเดือน → ตรวจรายบรรทัดเทียบระบบเดิม (ช่วง parallel run เทียบทุกงวด) → **Post**
   ใบสำคัญรวมยอด**ตามบัญชี** (rule หลายตัวที่ชี้บัญชีเดียวกัน เช่น OT 4 อัตรา ออกเป็นบรรทัดเดียว) แยกกอง Analytic ตามสาขา
9. ต้นเดือนถัดไป: จ่ายเงินเดือน `Dr 232001 / Cr ธนาคาร`, นำส่ง สปส. `Dr 232010 / Cr ธนาคาร`,
   นำส่ง ภงด.1 `Dr 231001 / Cr ธนาคาร`
   **ตัวเช็คที่ง่ายที่สุด: สามบัญชีค้างจ่ายนี้ต้องล้างเป็นศูนย์หลังจ่ายครบ** — มีเศษค้าง = มีอะไรผิด ตรวจก่อนปิดงวด

---

## 6. งานตั้งค่าภายหลัง (ทำเมื่อของมาครบ)

| งาน | วิธี |
|---|---|
| **เติมเงินเดือนจริง** (แทน wage=0) | HR กรอกคอลัมน์ "เงินเดือน (กรอก)" ใน `data/ready3/04_contract_data_to_fill.xlsx` → รัน `create_contracts_shell.py` ซ้ำ (อัปเดตเฉพาะคนที่ตัวเลขต่าง) |
| **ต้นทุนรายสาขา (Analytic)** | ✅ ตั้งแล้ว (27 ส.ค. 2026) ด้วย `set_contract_analytic_shell.py` — จับคู่รหัสสาขาพนักงานกับช่อง Code ของกอง Analytic อัตโนมัติ (AZG→H.O.) รันซ้ำเมื่อมีพนักงาน/สาขาใหม่ · สาขาใหม่ต้องสร้างกองพร้อมใส่ Code เป็นรหัสสาขาเสมอ |
| **เพิ่มรายได้/รายการหักใหม่** (Business Plus เพิ่มรหัสใหม่) | เพิ่ม 1 แถวใน `EARNINGS`/`DEDUCTIONS` ของ `gen_payroll_config.py` (รหัส BPlus, Odoo code, ชื่อสลิป, บัญชีกลุ่ม) → รัน generator → `-u import_payslip_inputs` → รัน wiring → ดึงไฟล์ใหม่ อย่าคลิกเพิ่มมือ (จะหลุดจากชุด generate) · รหัสที่ยอดเป็น 0 เสมอ (สถิติวันลา) ใส่ใน `BPLUS_SKIP` แทน |
| **แก้บัญชีของรายการเดิม** | บัญชีตรวจตาราง `doc/BPLUS_CODE_MAP.md` (แถว ★ = ใช้บัญชีกลุ่มไปก่อน) → แก้ที่ตารางแม็ปของ generator → generate + รัน wiring (หรือแก้ที่ rule ใน UI ชั่วคราวแล้วค่อยตามแก้ generator ให้ตรง ไม่งั้น wiring รอบหน้าทับกลับ) |
| **พนักงานลาออก** | Archive employee + ตั้ง End Date และปิดสัญญา — ห้ามลบ (ประวัติสลิปต้องอยู่) |
| **สลิปฟอร์มไทย** | รายงาน QWeb คัสตอมได้เต็มที่ ผูก template ต่อ structure ได้ (งานออกแบบแยก — เตรียมตัวอย่างสลิปเดิมให้ทีมพัฒนา) |

---

## 7. Troubleshooting (อาการจริงที่เคยเจอทั้งหมด)

| อาการ | สาเหตุจริง | ทางแก้ |
|---|---|---|
| ยืนยันสลิปแล้ว**ใบสำคัญว่างเปล่า** / แยกหลายใบ / ลงสมุด "Salaries" | ลืมรัน wiring หลัง restore DB (กฎเหล็กข้อ 1) | รัน `wire_payroll_accounts_shell.py` แล้ว smoke test |
| Import ฟ้อง "Record does not exist or has been deleted (resource.resource...)" ทุกแถว | **ไม่ใช่เรื่อง resource!** เป็น error รายงานเพี้ยนเมื่อ field บังคับว่าง (เคยเจอ: `marital`) — ของจริงอยู่ใน server log | เช็ค field บังคับในไฟล์ อย่าเสียเวลา restart |
| Import ฟ้อง "No matching record found for external id 'dept_...'" | ไฟล์แผนก (00a) ไม่ครบ path — มักเกิดจากไฟล์ HR มีสังกัดใหม่/แถวเก้าอี้ path ใหม่ | รัน converter ใหม่ (generate 00a ใหม่) แล้ว import ซ้ำ |
| "No matching record found ... in field 'User'" (ไฟล์ 03) | ชื่อในไฟล์ไม่ตรงชื่อ user เป๊ะ (จินตนา vs Jintana) | แก้ชื่อให้ตรง Settings → Users |
| Test ผ่านแต่ Import จริง error | แก้ไฟล์ Excel แล้วไม่ได้กด Load Data File ใหม่ (กรณี import ผ่าน UI) | โหลดไฟล์เวอร์ชันล่าสุดเสมอ |
| พนักงานซ้ำ 2 record | มี employee เดิมไม่ผูก External ID (จากการสร้าง user) | รัน `prepare_db_shell.py` ก่อน import ครั้งแรก |
| Avatar เป็นอักษรผิด | รูป placeholder ถูก store ตอนชื่อยังผิด | converter แยกคำนำหน้าก่อน import แล้ว ถ้าพลาด: ล้าง image_1920 |
| ผังองค์กรแสดงการ์ดแบนเต็มจอ ไม่เป็นต้นไม้ | มีคน "เป็นหัวหน้าตัวเอง" หรือคนไม่มีหัวหน้าจำนวนมาก | converter ข้าม self-parent ให้แล้ว / ที่เหลือดู FIX_REPORT |
| สลิปบางคนเป็นศูนย์ | คนนั้นไม่มีแถวในไฟล์ payroll (บ่อยสุด: กลุ่มจ่ายนอกระบบ/SRT) | HR เติมแถวในไฟล์แล้ว import ซ้ำ |
| wizard ฟ้อง "รายการหักเงินกู้...ห้ามใส่ในไฟล์" | ไฟล์มีรายการ LOAN ซึ่งโมดูลเงินกู้จัดการอยู่แล้ว (กันหักซ้ำ) | ตัดคอลัมน์/แถว LOAN ออกจากไฟล์ |
| สร้างสัญญาไม่ได้ ฟ้อง wage บังคับ | — | ใช้ `create_contracts_shell.py` (ใส่ 0 ให้อัตโนมัติ) |
| `bplus_extract.py` หยุด "ไม่พบงวด" | HR ยังไม่คำนวณ/ปิดงวดใน Business Plus หรือใส่เดือนผิด (เดือนของงวด = เดือนที่จ่าย) | รอ HR ปิดงวด / ตรวจ --year --month |
| `bplus_extract.py` หยุด "ยอดไม่ลงตัว N คน" | รหัสในตาราง map อยู่ผิดฝั่ง (รายได้↔รายหัก) หรือ BPlus มีรหัสใหม่ที่ map ไว้แบบ STAT แต่มียอดเงิน | ดูรหัสของคนที่ฟ้องในชีต BplusData/Skipped แล้วแก้ generator |
| wizard ฟ้อง "Control: พนักงาน X ยอดในไฟล์ ... ไม่เท่ากับ" | ไฟล์ถูกแก้มือหลัง extract หรือ rule ของรหัสนั้นไม่มีใน structure ของสลิป | extract ใหม่ / ตรวจว่า input code นั้นมี rule ใน 3 structures (รัน wiring) |
| ผลเทียบ NET "ไม่ตรง" ทั้งที่ Preview ผ่าน | rule ใน Odoo คำนวณต่างจากไฟล์ — มักเป็นรายการคีย์มือค้างในสลิป หรือโมดูลเงินกู้ push ยอดไม่เท่า BPlus | เปิดสลิปคนนั้น ดู Other Inputs ที่ไม่ได้มาจากไฟล์ |
| sqlcmd ต่อ SQL Server ไม่ได้ | เครื่องอยู่นอก LAN / ยังไม่สร้าง login odoo_reader | ต้องรันจากเครื่องในออฟฟิศ + รัน create_bplus_reader_login.sql ครั้งเดียวด้วย sa |
| ปุ่ม "ดึงจาก Business Plus" ฟ้อง "server นี้ยังไม่มี pyodbc" | ยังไม่ลง ODBC Driver + pyodbc ใน Python ของ Odoo | ลง msi "ODBC Driver 17 for SQL Server" + `python -m pip install pyodbc` + restart service |
| ปุ่มฟ้อง "ต่อ SQL Server ... ไม่ได้" (timeout) | Tailscale บนเครื่อง SQL Server ไม่ขึ้น / เครื่องปิด / bplus.server ผิด | ping IP Tailscale จาก server Odoo ก่อน; ระหว่างนั้นใช้ทางสำรอง (สคริปต์ + อัปโหลด) |
| ปุ่มฟ้อง "ไม่พบรหัสรายการ 'LATE'" หรือรหัสอื่นทั้งที่ map แล้ว | ลืมรัน wiring หลัง restore/-u (input type ยัง archive / rule ยังไม่ผูก) | รัน `wire_payroll_accounts_shell.py` (กฎเหล็กข้อ 1) |
| odoo shell พ่นภาษาไทยไม่ได้ / UnicodeEncodeError | คอนโซล Windows เป็น cp1252 | ใส่ `PYTHONUTF8=1` หน้าทุกคำสั่ง (ตามตัวอย่างในคู่มือ) |

---

## 8. ภาคผนวก

### ก. ค่าที่ระบบรับ (ถ้าแก้ไฟล์ ready เอง)
- วันที่ `YYYY-MM-DD` **ค.ศ.** | เพศ `male/female/other` | สมรส `single/married/cohabitant/widower/divorced` (ห้ามว่าง)
- วุฒิ: `primary_3, primary_6, secondary_3, secondary_6, nfe, vocational_cert, technical_cert, high_vocational, bachelor, master, doctor`
- จังหวัด `base.state_th_001..077` | ประเทศ `base.th / base.mm / base.kh / base.la`
- แผนก `dept_<hash>` (converter สร้าง อย่าพิมพ์เอง) | สาขา `wl_<รหัสสาขา>` | คอลัมน์เลขนำหน้า 0 = format Text

### ข. โครงโฟลเดอร์
```
custom_addons/import_payslip_inputs/
├── data/
│   ├── hr_payroll_structure_v3.xml   ← โครงสร้าง+rules (generate จาก gen_payroll_config.py อย่าแก้มือ)
│   └── ready3/                       ← ชุดไฟล์ import ปัจจุบัน + 04 + FIX_REPORT
├── tools/                            ← สคริปต์ทั้งหมด (ตารางหัวข้อ 2)
├── doc/
│   ├── IMPORT_GUIDE.md               ← คู่มือฉบับนี้
│   ├── ACCOUNT_MAPPING_CONFIRM.xlsx  ← ตารางบัญชีที่บัญชียืนยัน (แหล่งอ้างอิงเลขบัญชี)
│   └── ACCOUNT_MAPPING.md            ← โฟลว์บัญชี/ตาราง Dr-Cr ฉบับอ่าน
└── wizard/                           ← ปุ่ม Import Inputs (Excel) บนหน้า Batch
D:\odoo18\other\                      ← ไฟล์ดิบจาก HR/บัญชี (ต้นทางของ converter)
```
`tools/gen_payroll_config.py` = **แหล่งความจริงเดียวของตารางแม็ปบัญชี** — แก้รายได้/รายการหัก/เลขบัญชีที่ตารางในไฟล์นี้
แล้วรัน (แบบ python ปกติ) เพื่อ generate `data/hr_payroll_structure_v3.xml` + `tools/wire_payroll_accounts_shell.py` ใหม่
จากนั้น upgrade โมดูล + รัน wiring + smoke test
```
```

### ค. สโมคเทสต์อ่านผลยังไง
รันแล้วต้องเห็น `***** ผลทดสอบ: ผ่าน *****` = ใบสำคัญ 1 ใบ สมุดเงินเดือน ดุล 115,275 ทั้งสองฝั่ง
พร้อมบรรทัด Dr/Cr ครบตามหัวสคริปต์ — "ไม่ผ่าน" ให้ไล่ตามหัวข้อ 7 บรรทัดแรกก่อนเสมอ
