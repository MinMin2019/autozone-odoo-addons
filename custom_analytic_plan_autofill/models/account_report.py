from odoo import models


class AccountReport(models.AbstractModel):
    _inherit = "account.report"

    def _create_column_analytic(self, options):
        # Enterprise เรียง slice เป็น "แผนทั้งหมดก่อน แล้วค่อยบัญชีทั้งหมด"
        # (ZONE1 ZONE2 | BPH BHA TYB ...) — จัดใหม่ให้แต่ละโซนตามด้วยสาขาของตัวเอง
        # (ZONE1 BPH BHA | ZONE2 TYB ...) สาขาที่ไม่สังกัดโซนที่เลือกไปต่อท้าย
        super()._create_column_analytic(options)
        for level in options.get("column_headers", []):
            positions = [
                i for i, header in enumerate(level)
                if (header.get("forced_options") or {}).get("analytic_groupby_option")
            ]
            # ตัดคอลัมน์ "ทั้งบริษัท" (หัวว่างที่ Enterprise เติมท้าย slice) ออก —
            # ฝ่ายบัญชีต้องการเห็นเฉพาะโซน/สาขาที่เลือก
            if positions:
                for i in range(len(level) - 1, -1, -1):
                    if not level[i].get("name") and not level[i].get("forced_options"):
                        level.pop(i)
                positions = [
                    i for i, header in enumerate(level)
                    if (header.get("forced_options") or {}).get("analytic_groupby_option")
                ]
            if len(positions) < 2:
                continue
            plans, accounts = [], []
            for i in positions:
                forced = level[i]["forced_options"]
                if "analytic_plan_id" in forced:
                    plans.append(level[i])
                else:
                    accounts.append(level[i])
            if not plans or not accounts:
                continue
            reordered, used = [], set()
            for plan_header in plans:
                member_ids = set(plan_header["forced_options"].get("analytic_accounts_list") or ())
                reordered.append(plan_header)
                for j, account_header in enumerate(accounts):
                    account_ids = account_header["forced_options"].get("analytic_accounts_list") or ()
                    if j not in used and len(account_ids) == 1 and account_ids[0] in member_ids:
                        used.add(j)
                        reordered.append(account_header)
            reordered.extend(h for j, h in enumerate(accounts) if j not in used)
            for i, header in zip(positions, reordered):
                level[i] = header
