from odoo import models


class AccountReport(models.AbstractModel):
    _inherit = "account.report"

    def _create_column_analytic(self, options):
        # หัวคอลัมน์ slice รายสาขาใช้ชื่อเต็ม ("ฮอนด้า บางปู") กินที่มากเวลาเปิดหลายสาขา
        # ย่อเหลือรหัส (BPH) แบบเดียวกับชิปในฟิลเตอร์ — หัวโซน (plan เช่น ZONE 1) คงเดิม
        super()._create_column_analytic(options)
        for level in options.get("column_headers", []):
            for header in level:
                forced = header.get("forced_options") or {}
                if not forced.get("analytic_groupby_option") or "analytic_plan_id" in forced:
                    continue
                account_list = forced.get("analytic_accounts_list") or ()
                if len(account_list) == 1:
                    account = self.env["account.analytic.account"].browse(account_list[0])
                    if account.code:
                        header["name"] = account.code
