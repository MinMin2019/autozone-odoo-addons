# -*- coding: utf-8 -*-
"""ตรวจ/สร้าง Account Groups จากผังแม่ แบบไม่ต้องเปิดหน้าจอ

ค่าเริ่มต้นคือ "ตรวจอย่างเดียว" (dry-run) — พิมพ์แผนออกมาแล้วจบ
ถ้าจะให้ลงมือจริงต้องตั้ง AZ_APPLY=1 ก่อนรัน

เครื่อง dev (Git Bash):
  PYTHONUTF8=1 ./odoo-venv/Scripts/python.exe odoo-bin shell -c odoo.conf \
    -d Autozone-PD --no-http \
    < custom_addons/custom_account_hierarchy_fix/scripts/sync_account_groups.py

production ใช้ cmd.exe redirect stdin ตามวิธีใน [[prod-server-ssh]] (ห้าม PowerShell — BOM)
"""

import os

env = env  # noqa: F821

Sync = env["az.account.group.sync"]
plan = Sync._az_build_plan(
    min_prefix_len=int(os.environ.get("AZ_MIN_PREFIX_LEN", 2)),
    include_childless_views=os.environ.get("AZ_INCLUDE_CHILDLESS", "1") == "1",
    purge_others=os.environ.get("AZ_PURGE", "1") == "1",
)
print(Sync._az_format_plan(plan))

if os.environ.get("AZ_APPLY") == "1":
    Sync._az_apply_plan(plan)
    env.cr.commit()
    print("\n=== ลงมือแล้ว (commit) — ตรวจซ้ำ ===\n")
    print(Sync._az_format_plan(Sync._az_build_plan(
        min_prefix_len=int(os.environ.get("AZ_MIN_PREFIX_LEN", 2)),
        include_childless_views=os.environ.get("AZ_INCLUDE_CHILDLESS", "1") == "1",
        purge_others=os.environ.get("AZ_PURGE", "1") == "1",
    )))
else:
    print("\n(ตรวจอย่างเดียว ยังไม่แก้อะไร — ตั้ง AZ_APPLY=1 ถ้าจะลงมือจริง)")
