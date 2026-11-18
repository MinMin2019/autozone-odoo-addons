import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# xmlid: (English, ไทย) — ตั้งตามแบบงบกำไรขาดทุนที่ใช้ในไทย (TFRS for NPAEs)
# หัวข้อไม่ใส่คำ "หัก/บวก" เพราะ Odoo เติม "Total"/"รวม" หน้าชื่อหัวข้อเองในบรรทัดยอดรวม
REPORT_LABELS = {
    "account_reports.profit_and_loss": ("Profit and Loss", "งบกำไรขาดทุน"),
}

LINE_LABELS = {
    # บรรทัดมาตรฐานของ Odoo
    "account_reports.account_financial_report_revenue0": (
        "Revenue", "รายได้"),
    "account_reports.account_financial_report_cost_sales0": (
        "Cost of Sales and Services", "ต้นทุนขายและบริการ"),
    "account_reports.account_financial_report_gross_profit0": (
        "Gross Profit", "กำไรขั้นต้น"),
    "account_reports.account_financial_report_expense0": (
        "Selling and Administrative Expenses", "ค่าใช้จ่ายในการขายและบริหาร"),
    "account_reports.account_financial_report_operating_income0": (
        "Operating Profit (Loss)", "กำไร (ขาดทุน) จากการดำเนินงาน"),
    "account_reports.account_financial_report_other_income0": (
        "Other Income", "รายได้อื่น"),
    # บรรทัดนี้ดึงเฉพาะบัญชีประเภท Depreciation จึงตั้งชื่อตามเนื้อจริง
    "account_reports.account_financial_report_depreciation0": (
        "Depreciation and Amortization", "ค่าเสื่อมราคาและค่าตัดจำหน่าย"),
    "account_reports.account_financial_report_net_profit0": (
        "Net Profit (Loss)", "กำไร (ขาดทุน) สุทธิ"),
    # โครงใหม่ใน data/profit_and_loss_structure.xml
    "custom_report_pl_labels.pl_exp_selling": (
        "Selling Expenses", "ค่าใช้จ่ายในการขาย"),
    "custom_report_pl_labels.pl_exp_admin": (
        "Administrative Expenses", "ค่าใช้จ่ายในการบริหาร"),
    "custom_report_pl_labels.pl_exp_misc": (
        "Other Expenses (Unmapped Account Codes)", "ค่าใช้จ่ายอื่น (รหัสนอกช่วง)"),
    "custom_report_pl_labels.pl_line_finance_cost": (
        "Finance Costs", "ต้นทุนทางการเงิน"),
    "custom_report_pl_labels.pl_line_ebt": (
        "Net Profit (Loss) before Income Tax", "กำไร (ขาดทุน) สุทธิก่อนภาษีเงินได้"),
    "custom_report_pl_labels.pl_line_income_tax": (
        "Income Tax Expense", "ค่าใช้จ่ายภาษีเงินได้"),
    # custom_report_ebda — ชื่อไทยตามที่ฝ่ายบัญชีกำหนด 17 พ.ย. 2026
    "custom_report_ebda.pl_line_ebda": (
        "Earnings before Interest, Tax, Depreciation and Amortization (EBITDA)",
        "กำไรก่อนดอกเบี้ย ภาษีเงินได้ ค่าเสื่อมราคาและรายการตัดบัญชี (EBITDA)"),
    # custom_report_pl_cost_groups — ชื่อไทยคงตามที่ฝ่ายบัญชีกำหนด
    "custom_report_pl_cost_groups.pl_cos_labor": (
        "Direct Labor", "ค่าแรงงานทางตรง"),
    "custom_report_pl_cost_groups.pl_cos_welfare": (
        "Employee Benefits", "ค่าสวัสดิการพนักงาน"),
    "custom_report_pl_cost_groups.pl_cos_parts": (
        "Spare Parts", "ค่าอะไหล่"),
    "custom_report_pl_cost_groups.pl_cos_paint": (
        "Paint", "ค่าสี"),
    "custom_report_pl_cost_groups.pl_cos_supply": (
        "Factory Supplies", "ค่าวัสดุสิ้นเปลืองโรงงาน"),
    "custom_report_pl_cost_groups.pl_cos_other_prod": (
        "Other Production Overhead", "ค่าใช้จ่ายผลิตอื่น"),
    "custom_report_pl_cost_groups.pl_cos_misc": (
        "Other Costs (Unmapped Account Codes)", "ต้นทุนอื่น (รหัสนอกช่วง)"),
}


class AccountReportLine(models.Model):
    _inherit = "account.report.line"

    @api.model
    def _az_apply_pl_labels(self):
        active_langs = {code for code, _name in self.env["res.lang"].get_installed()}
        for labels in (REPORT_LABELS, LINE_LABELS):
            for xmlid, (en, th) in labels.items():
                record = self.env.ref(xmlid, raise_if_not_found=False)
                if not record:
                    _logger.warning("P&L labels: ไม่พบ %s ข้าม", xmlid)
                    continue
                translations = {"en_US": en}
                if "th_TH" in active_langs:
                    translations["th_TH"] = th
                record.update_field_translations("name", translations)
        return True
