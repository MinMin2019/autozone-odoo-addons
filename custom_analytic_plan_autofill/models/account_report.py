import re

from odoo import models


def _natural_key(name):
    """ คีย์เรียงแบบธรรมชาติ: "1 IKM" < "2 IKR" < "10 XXX" (ไม่ใช่ 1, 10, 2)
    ตัวเลขในชื่อเทียบเป็นจำนวน ตัวอักษรเทียบแบบไม่สนพิมพ์เล็ก/ใหญ่ """
    parts = re.split(r"(\d+)", (name or "").strip())
    return tuple((0, int(part)) if part.isdigit() else (1, part.lower()) for part in parts)


class AccountReport(models.AbstractModel):
    _inherit = "account.report"

    def _az_analytic_header_sort_key(self, header):
        """ คีย์เรียงหัวคอลัมน์สาขา: มีเลขนำหน้าในชื่อหรือรหัส -> เรียงตามเลขนั้น (natural),
        ไม่มีเลข -> ต่อท้ายเรียงตามชื่อ """
        account_ids = (header.get("forced_options") or {}).get("analytic_accounts_list") or ()
        account = self.env["account.analytic.account"].browse(account_ids[0]) if len(account_ids) == 1 else None
        if account is None:
            return (2, _natural_key(header.get("name")))
        for text in (account.name, account.code):
            if text and re.match(r"\s*\d", text):
                return (0, _natural_key(text))
        return (1, _natural_key(account.name))

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
            # เรียงสาขาตามเลขลำดับที่บัญชีใส่นำหน้าไว้ (เช่น "1 IKM") แทนกฎ Odoo ที่เรียง
            # ตามแผนก่อนแล้วค่อยชื่อ — อ่านจาก record ตรง ๆ ไม่ใช่หัวคอลัมน์ เพราะโมดูลอื่น
            # (custom_analytic_code_tags) อาจแทนหัวด้วยรหัสไปแล้ว; เรียงทั้งกรณีเลือกโซนและไม่เลือก
            accounts.sort(key=self._az_analytic_header_sort_key)
            if not plans or not accounts:
                if accounts:
                    for i, header in zip(positions, plans + accounts):
                        level[i] = header
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
