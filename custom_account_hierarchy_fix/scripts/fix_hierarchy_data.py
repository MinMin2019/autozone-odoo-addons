# -*- coding: utf-8 -*-
"""ซ่อมข้อมูล Parent Account (sh_parent_id) ที่เสียอยู่ก่อนติดตั้ง constraint:
1. หัวชั้นที่ชี้ตัวเอง → ล้างเป็นหัวชั้นบนสุด (ต้นเหตุรายงาน hierarchy ว่าง/ไม่กาง)
2. รายการซ่อมเฉพาะจุด (parent ชี้ผิดตัว) — แก้ลิสต์ REPAIRS ตาม DB นั้น ๆ
3. พิมพ์สรุปสุขภาพที่เหลือ (parent ไม่ใช่ view / บัญชีไม่มี parent) ให้ตัดสินใจต่อ

รันซ้ำได้ (idempotent) — Git Bash เครื่อง dev:
  PYTHONUTF8=1 ./odoo-venv/Scripts/python.exe odoo-bin shell -c odoo.conf \
    -d <DB> --no-http < custom_addons/custom_account_hierarchy_fix/scripts/fix_hierarchy_data.py
เครื่อง server ใช้ cmd.exe (ห้าม PowerShell — BOM) ตามวิธีในโมดูล custom_petty_cash
"""

env = env  # noqa: F821

A = env["account.account"].with_context(active_test=False)

# 1) หัวชั้นชี้ตัวเอง
self_linked = A.search([]).filtered(lambda a: a.sh_parent_id == a)
for acc in self_linked:
    acc.sh_parent_id = False
    print(f"ล้างชี้ตัวเอง: {acc.code} {acc.name}")

# 2) ซ่อมเฉพาะจุด: (code ลูก, code parent ที่ถูก)
REPAIRS = [
    ("176001", "176000"),  # เครื่องใช้สำนักงาน — เดิมชี้ 171000 ที่ดิน (เลือกผิดแถว)
    ("532400", "530000"),  # ส่วนต่างจากการปรับราคา — เดิมไม่มี parent
]
for child_code, parent_code in REPAIRS:
    child = A.search([("code", "=", child_code)], limit=1)
    parent = A.search([("code", "=", parent_code)], limit=1)
    if not child or not parent:
        print(f"ข้าม {child_code}->{parent_code}: หาไม่เจอใน DB นี้")
        continue
    if child.sh_parent_id == parent:
        print(f"ข้าม {child_code}: ถูกอยู่แล้ว")
        continue
    old = child.sh_parent_id.code or "-"
    child.sh_parent_id = parent
    print(f"ซ่อม {child_code} {child.name}: parent {old} -> {parent_code}")

env.cr.commit()

# 3) สรุปสุขภาพที่เหลือ
bad_parent = A.search([("sh_parent_id", "!=", False)]).filtered(
    lambda a: a.sh_parent_id.account_type != "view")
if bad_parent:
    print("\n!! ยังมี parent ที่ไม่ใช่ view (เพิ่มเข้า REPAIRS แล้วรันใหม่):")
    for a in bad_parent:
        print(f"  {a.code} {a.name} -> {a.sh_parent_id.code} ({a.sh_parent_id.account_type})")

tops = A.search([("sh_parent_id", "=", False), ("account_type", "=", "view")],
                order="code")
print(f"\nหัวชั้นบนสุด (view) {len(tops)} ตัว: "
      + ", ".join(tops.mapped("code")))
orphans = A.search([("sh_parent_id", "=", False), ("account_type", "!=", "view")])
print(f"บัญชีปกติที่ไม่มี parent (จะโชว์แบนที่ระดับบนสุด): {len(orphans)} ตัว")
empty_views = A.search([("account_type", "=", "view")]).filtered(
    lambda v: not A.search_count([("sh_parent_id", "=", v.id)]))
if empty_views:
    print("view ที่ไม่มีลูกเลย: "
          + ", ".join(f"{v.code} {v.name}" for v in empty_views))
print("เสร็จ")
