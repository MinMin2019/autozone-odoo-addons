from odoo import models
from odoo.tools import float_is_zero


class AccountReport(models.AbstractModel):
    _inherit = "account.report"

    def _init_options_columns(self, options, previous_options):
        # Enterprise วางหัวงบประมาณไว้ชั้นล่างสุด: [analytic..., "" (budget_base = ทั้งบริษัท), งบ, %]
        # - เลือก analytic อยู่: ตัดคอลัมน์ทั้งบริษัททิ้ง ฝ่ายบัญชีดูเฉพาะสาขา/โซนที่เลือก
        # - หัว % เปลี่ยนเป็น "ผลต่าง" (ค่าคำนวณใน _set_budget_column_comparisons)
        if any(budget.get("selected") for budget in options.get("budgets", [])) and options.get("column_headers"):
            level = options["column_headers"][-1]
            has_analytic = any((h.get("forced_options") or {}).get("analytic_groupby_option") for h in level)
            if has_analytic:
                level[:] = [h for h in level if not (h.get("forced_options") or {}).get("budget_base")]
            for header in level:
                if "budget_percentage" in (header.get("forced_options") or {}):
                    header["name"] = "ผลต่าง"
        super()._init_options_columns(options, previous_options)

    def _set_budget_column_comparisons(self, options, line):
        """ แทนค่า % ด้วยผลต่าง = ยอดจริง − งบประมาณ """
        column_groups = options["column_groups"]
        for col_index, col in enumerate(line["columns"]):
            forced = column_groups[col["column_group_key"]].get("forced_options") or {}
            if "budget_percentage" not in forced:
                continue
            budget_id = forced["budget_percentage"]
            date_key = forced.get("date")
            if not date_key:
                continue

            base_cols, plan_cols, account_cols, budget_col = [], [], [], None
            for line_col in line["columns"]:
                other = column_groups[line_col["column_group_key"]].get("forced_options") or {}
                if other.get("date") != date_key:
                    continue
                if other.get("compute_budget") == budget_id:
                    budget_col = line_col
                elif line_col.get("figure_type") != "monetary":
                    continue
                elif other.get("budget_base"):
                    base_cols.append(line_col)
                elif other.get("analytic_groupby_option"):
                    (plan_cols if "analytic_plan_id" in other else account_cols).append(line_col)

            # ยอดจริง: คอลัมน์ทั้งบริษัท (ไม่ได้เลือก analytic) > ผลรวมสาขา > ผลรวมโซน
            actual_cols = base_cols or account_cols or plan_cols
            if budget_col is None or not actual_cols:
                continue
            values = [c.get("no_format") for c in actual_cols]
            budget_value = budget_col.get("no_format")
            if all(v is None for v in values) and budget_value is None:
                variance, mode = None, None
            else:
                variance = sum(v or 0.0 for v in values) - (budget_value or 0.0)
                green_on_positive = actual_cols[0].get("green_on_positive", True)
                if float_is_zero(variance, precision_digits=2):
                    mode = "muted"
                else:
                    mode = "green" if (variance > 0) == bool(green_on_positive) else "red"

            new_col = {
                **budget_col,
                "no_format": variance,
                "is_zero": variance is None or float_is_zero(variance, precision_digits=2),
                "figure_type": "monetary",
                "auditable": False,
                "comparison_mode": mode,
                "column_group_key": col["column_group_key"],
            }
            new_col.pop("name", None)
            new_col.pop("edit_popup_data", None)
            line["columns"][col_index] = new_col
