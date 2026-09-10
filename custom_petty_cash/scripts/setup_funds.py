# -*- coding: utf-8 -*-
"""ตั้งค่ากองเงินสดย่อย 27 สาขา (รันครั้งเดียวหลังติดตั้งโมดูล custom_petty_cash)

สร้างให้ครบชุดต่อสาขา:
  - cash journal "PCxxx เงินสดย่อย <สาขา>" default account = 111002 Petty Cash
    + outstanding ทั้งฝั่งจ่าย/รับ = 111001 บัญชีพักเงินจ่าย (กันเหตุกด Pay แล้ว JE ไม่เกิด)
  - petty.cash.fund วงเงิน 4,000 ผูก journal + analytic ของสาขา
และสร้าง purchase journal กลาง "PCB ตั้งหนี้เงินสดย่อย" หนึ่งใบ ใช้ร่วมทุกสาขา
(PCB ปกติถูกสร้างให้แล้วตอนติดตั้ง/อัพเกรดโมดูล — สคริปต์สร้างซ้ำให้ถ้ายังไม่มี)

วิธีรัน — ต้อง PYTHONUTF8=1 และ **ห้าม pipe ผ่าน PowerShell** (จะแทรก BOM แล้วพัง)

เครื่อง dev (Git Bash ที่ d:/odoo18):
  PYTHONUTF8=1 ./odoo-venv/Scripts/python.exe odoo-bin shell -c odoo.conf \
    -d Autozone-PD --no-http < custom_addons/custom_petty_cash/scripts/setup_funds.py

เครื่อง server (Odoo installer — เปิด **cmd.exe** ไม่ใช่ PowerShell):
  cd "C:\Program Files\Odoo 18.0.20260105\server"
  set PYTHONUTF8=1
  ..\python\python.exe odoo-bin shell -c odoo.conf -d <ชื่อDB> --no-http ^
    < <path>\custom_addons\custom_petty_cash\scripts\setup_funds.py

เงื่อนไขก่อนรัน: ติดตั้งโมดูล custom_petty_cash (≥1.5.0) ใน DB นั้นแล้ว และ DB ต้องมี
analytic account 27 สาขา + บัญชี 111002 (DB ก๊อปจาก production มีครบ)
รันซ้ำได้ (idempotent): ข้ามสาขาที่มี journal/fund อยู่แล้ว
"""

import re

env = env  # noqa: F821 — มาจาก odoo shell

from odoo.addons.custom_petty_cash.hooks import _setup_petty_cash_outstanding

company = env.ref("base.main_company")
Journal = env["account.journal"].with_company(company)
Fund = env["petty.cash.fund"]

petty_account = env["account.account"].with_company(company).search(
    [("code", "=", "111002")], limit=1)
assert petty_account, "ไม่พบบัญชี 111002 Petty Cash"

# บัญชีพัก 111001 + journal PCB — ปกติมีแล้ว สร้างซ้ำให้ถ้าขาด
outstanding_account = _setup_petty_cash_outstanding(env)
print(f"บัญชีพักเงินจ่าย: {outstanding_account.code} {outstanding_account.name}")

bill_journal = Journal.search([("code", "=", "PCB"), ("type", "=", "purchase")], limit=1)
assert bill_journal, "ไม่พบ purchase journal PCB (hook ควรสร้างให้แล้ว)"

branches = env["account.analytic.account"].search(
    [("plan_id.name", "!=", "Project")])
print(f"พบสาขา {len(branches)} รายการ")

created = skipped = 0
for aa in branches:
    code = re.sub(r"[^A-Za-z0-9]", "", aa.code or "").upper()
    if not code:
        print(f"  ข้าม {aa.name}: ไม่มีรหัส")
        continue
    jcode = ("PC" + code)[:5]

    journal = Journal.search([("code", "=", jcode)], limit=1)
    if not journal:
        journal = Journal.create({
            "name": f"เงินสดย่อย {aa.name}",
            "code": jcode,
            "type": "cash",
            "company_id": company.id,
            "default_account_id": petty_account.id,
        })
        for line in (journal.inbound_payment_method_line_ids
                     + journal.outbound_payment_method_line_ids):
            if not line.payment_account_id:
                line.payment_account_id = outstanding_account.id

    fund = Fund.with_context(active_test=False).search(
        [("code", "=", code), ("company_id", "=", company.id)], limit=1)
    if fund:
        skipped += 1
        continue
    Fund.create({
        "name": aa.name,
        "code": code,
        "amount_limit": 4000.0,
        "journal_id": journal.id,
        "bill_journal_id": bill_journal.id,
        "analytic_account_id": aa.id,
        "company_id": company.id,
    })
    created += 1
    print(f"  + [{code}] {aa.name} (journal {jcode})")

env.cr.commit()
print(f"เสร็จ: สร้างกองใหม่ {created}, มีอยู่แล้ว {skipped}")
