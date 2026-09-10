from odoo import fields, models, _
from odoo.tools import float_is_zero, float_repr

# expression_label ของคอลัมน์ที่ฉีดเพิ่ม — ต้องไม่ชนกับ label จริงของรายงานใด
PCT_EXPR_LABEL = "az_growth_pct"        # % เปลี่ยนแปลงเทียบงวดก่อน (horizontal)
CS_EXPR_LABEL = "az_common_size_pct"    # % สัดส่วนต่อบรรทัดฐาน (common-size / vertical)


class AccountReport(models.Model):
    _inherit = "account.report"

    az_common_size_base_line_id = fields.Many2one(
        "account.report.line",
        string="Common-size Base Line",
        help="บรรทัดที่ใช้เป็นฐาน 100% ของคอลัมน์ % common-size "
             "เช่น รายได้รวมใน P&L หรือสินทรัพย์รวมใน Balance Sheet — เว้นว่าง = ไม่แสดงคอลัมน์นี้",
    )
    az_common_size_label = fields.Char(
        string="Common-size Column Label",
        default="%",
        help="หัวคอลัมน์ % common-size เช่น %ขาย หรือ %สินทรัพย์",
    )

    # ------------------------------------------------------------------
    # Options: ฉีดคอลัมน์ % ต่อท้ายแต่ละงวด
    #   - ±% : เปลี่ยนแปลงเทียบงวดก่อนหน้า (เมื่อเปิด Comparison)
    #   - %  : common-size สัดส่วนต่อบรรทัดฐาน (เมื่อรายงาน config ฐานไว้)
    #
    # ฉีดที่ sequence 1080 (หลัง _init_options_custom = 1050) เพราะ handler
    # บางตัว เช่น Trial Balance สร้าง column group Initial/End Balance
    # คร่อมงวดตอน 1050 — ต้องเห็นโครงคอลัมน์สุดท้ายก่อนค่อยฉีด
    # ------------------------------------------------------------------
    def _get_options_initializers_forced_sequence_map(self):
        sequence_map = super()._get_options_initializers_forced_sequence_map()
        sequence_map[self._init_options_az_growth_percent] = 1080
        return sequence_map

    def _az_percent_columns_allowed(self, options):
        return (
            options.get("selected_horizontal_group_id") is None
            and not any(budget.get("selected") for budget in options.get("budgets", []))
            and options.get("column_percent_comparison") != "budget"
        )

    @staticmethod
    def _az_base_value(cells_by_label):
        """ ยอดฐานที่ใช้เทียบ % ของ group หนึ่ง: balance ถ้ามี ไม่งั้น debit - credit (Trial Balance) """
        balance = cells_by_label.get("balance")
        if balance is not None:
            return balance
        debit, credit = cells_by_label.get("debit"), cells_by_label.get("credit")
        if isinstance(debit, (int, float)) or isinstance(credit, (int, float)):
            return (debit or 0.0) - (credit or 0.0)
        return None

    def _init_options_az_growth_percent(self, options, previous_options):
        if not self._az_percent_columns_allowed(options):
            return

        group_keys = list(dict.fromkeys(col["column_group_key"] for col in options["columns"]))
        cols_by_group = {
            key: [col for col in options["columns"] if col["column_group_key"] == key]
            for key in group_keys
        }

        # --- ±% เทียบงวดก่อน: ต้องเปิด growth filter + มีงวดเปรียบเทียบ ---
        growth_ok = (
            self.filter_growth_comparison
            and len(options.get("comparison", {}).get("periods", [])) >= 1
        )
        if growth_ok:
            # group ที่เป็น "งวดจริง" = forced date ตรงกับงวดปัจจุบัน/งวดเปรียบเทียบเป๊ะ ๆ
            # (คัด Initial/End Balance ของ Trial Balance ออก — ช่วงวันที่ไม่ตรงกับงวดไหน)
            period_date_pairs = {
                (p.get("date_from"), p.get("date_to"))
                for p in [options["date"], *options["comparison"]["periods"]]
            }
            period_keys = []
            for key in group_keys:
                # บาง group ไม่มีใน column_groups โดยตั้งใจ เช่น End Balance ของ Trial Balance
                forced_date = options["column_groups"].get(key, {}).get("forced_options", {}).get("date") or {}
                if (forced_date.get("date_from"), forced_date.get("date_to")) in period_date_pairs:
                    period_keys.append(key)

            # ทุกงวดจริงต้องมีคอลัมน์ balance หรือคู่ debit/credit ให้คำนวณฐาน
            for key in period_keys:
                labels = {col["expression_label"] for col in cols_by_group[key]}
                if "balance" not in labels and not {"debit", "credit"} <= labels:
                    growth_ok = False
                    break
            if len(period_keys) < 2:
                growth_ok = False

        # --- % common-size: ต้อง config บรรทัดฐานไว้ที่ตัวรายงาน ---
        cs_ok = bool(self.az_common_size_base_line_id)

        if not growth_ok and not cs_ok:
            return

        if growth_ok:
            # ปิดกลไก % เดี่ยวท้ายตารางของ Enterprise แล้วใช้ของเราแทน
            options.pop("column_percent_comparison", None)

            # จับคู่ "งวดก่อนหน้า" เฉพาะ group ที่มิติอื่นเหมือนกันทุกอย่างยกเว้นวันที่ —
            # ไม่งั้นตอนเปิด Analytic Group By (งวดละหลาย group เช่น ZONE 1 กับทั้งบริษัท)
            # จะไปเทียบข้าม slice กันมั่ว
            def _identity(key):
                group = options["column_groups"].get(key) or {}
                forced = {k: v for k, v in (group.get("forced_options") or {}).items() if k != "date"}
                return repr((sorted(forced.items()), group.get("forced_domain")))

            chains = {}
            for key in sorted(
                period_keys,
                key=lambda k: options["column_groups"][k]["forced_options"]["date"]["date_to"],
            ):
                chains.setdefault(_identity(key), []).append(key)

            prev_map = {}
            for chain in chains.values():
                for i, key in enumerate(chain):
                    prev_map[key] = chain[i - 1] if i > 0 else None
            options["az_growth_percent"] = {"prev_map": prev_map}
        if cs_ok:
            options["az_common_size"] = {"base_line_id": self.az_common_size_base_line_id.id}

        # ฉีดคอลัมน์ให้ "ทุก" group (group ที่ไม่เข้าเงื่อนไขจะเว้นค่าว่าง) เพราะ
        # colspan ของหัวงวดคำนวณจากจำนวนคอลัมน์ของ group แรกแล้วใช้ร่วมกันทุก group
        def _pct_col(key, label, expression_label):
            return {
                "name": label,
                "column_group_key": key,
                "expression_label": expression_label,
                "sortable": False,
                "figure_type": "percentage",
                "blank_if_zero": False,
                "style": "text-align: center; white-space: nowrap;",
            }

        new_columns = []
        for key in group_keys:
            new_columns.extend(cols_by_group[key])
            if growth_ok:
                new_columns.append(_pct_col(key, "±%", PCT_EXPR_LABEL))
            if cs_ok:
                new_columns.append(_pct_col(key, self.az_common_size_label or "%", CS_EXPR_LABEL))
        options["columns"] = new_columns

    # ------------------------------------------------------------------
    # Lines: เติมค่า % หลังคำนวณบรรทัดเสร็จ
    # ------------------------------------------------------------------
    def _get_lines(self, options, all_column_groups_expression_totals=None, warnings=None):
        lines = super()._get_lines(
            options,
            all_column_groups_expression_totals=all_column_groups_expression_totals,
            warnings=warnings,
        )
        if options.get("az_growth_percent") or options.get("az_common_size"):
            self._az_fill_percent_columns(options, lines)
        return lines

    def get_expanded_lines(self, options, line_dict_id, groupby, expand_function_name, progress, offset, horizontal_split_side):
        # บรรทัดที่ผู้ใช้กดกางเอง (groupby รายบัญชี / load more) ไม่ผ่าน _get_lines
        # ต้องเติม % ให้ชุดบรรทัดที่กางมาด้วย
        lines = super().get_expanded_lines(
            options, line_dict_id, groupby, expand_function_name, progress, offset, horizontal_split_side,
        )
        if options.get("az_growth_percent") or options.get("az_common_size"):
            self._az_fill_percent_columns(options, lines)
        return lines

    def _az_fill_percent_columns(self, options, lines):
        pct_index = {}
        cs_index = {}
        value_indexes = {}  # {group_key: {expression_label: column_index}}
        for idx, col in enumerate(options["columns"]):
            key = col["column_group_key"]
            if col["expression_label"] == PCT_EXPR_LABEL:
                pct_index[key] = idx
            elif col["expression_label"] == CS_EXPR_LABEL:
                cs_index[key] = idx
            elif col["expression_label"] in ("balance", "debit", "credit"):
                value_indexes.setdefault(key, {})[col["expression_label"]] = idx

        raw_mode = options.get("export_mode") == "file"
        n_columns = len(options["columns"])

        def base_value(columns, key):
            cells_by_label = {}
            for label, v_idx in value_indexes.get(key, {}).items():
                cell = columns[v_idx]
                cells_by_label[label] = cell.get("no_format") if isinstance(cell, dict) else None
            return self._az_base_value(cells_by_label)

        def set_cell(cell, data):
            cell.update({
                "name": data["no_format"] if raw_mode and data["no_format"] is not None else data["name"],
                "no_format": data["no_format"],
                "comparison_mode": data.get("mode"),
                "is_zero": data["no_format"] is None,
            })

        blank = {"name": "", "no_format": None, "mode": None}

        # --- ±% เทียบงวดก่อน ---
        if options.get("az_growth_percent") and pct_index:
            prev_map = options["az_growth_percent"]["prev_map"]
            for line in lines:
                columns = line.get("columns") or []
                if len(columns) != n_columns:
                    continue
                for key, p_idx in pct_index.items():
                    cell = columns[p_idx]
                    if not isinstance(cell, dict) or not cell:
                        continue
                    prev_key = prev_map.get(key)  # group นอกงวดจริง (Initial/End Balance) ไม่อยู่ใน map
                    cur_value = base_value(columns, key)
                    if prev_key is None or not isinstance(cur_value, (int, float)):
                        # งวดแรกสุด / group ที่ไม่ใช่งวดจริง / บรรทัดหัวข้อไม่มีตัวเลข
                        set_cell(cell, blank)
                        continue
                    green_on_positive = True
                    balance_idx = value_indexes.get(key, {}).get("balance")
                    if balance_idx is not None and isinstance(columns[balance_idx], dict):
                        green_on_positive = columns[balance_idx].get("green_on_positive", True)
                    set_cell(cell, self._az_growth_percent_data(
                        cur_value, base_value(columns, prev_key),
                        green_on_positive=green_on_positive,
                    ))

        # --- % common-size ---
        if options.get("az_common_size") and cs_index:
            base_line_id = options["az_common_size"]["base_line_id"]
            base_by_group = self._az_find_common_size_bases(options, lines, base_line_id, value_indexes)
            for line in lines:
                columns = line.get("columns") or []
                if len(columns) != n_columns:
                    continue
                for key, c_idx in cs_index.items():
                    cell = columns[c_idx]
                    if not isinstance(cell, dict) or not cell:
                        continue
                    balance_idx = value_indexes.get(key, {}).get("balance")
                    value = columns[balance_idx].get("no_format") if balance_idx is not None and isinstance(columns[balance_idx], dict) else None
                    base = base_by_group.get(key)
                    if (
                        not isinstance(value, (int, float))
                        or not isinstance(base, (int, float))
                        or float_is_zero(base, precision_rounding=0.1)
                    ):
                        set_cell(cell, blank)
                        continue
                    ratio = round(value / base * 100, 1)
                    if float_is_zero(ratio, precision_digits=1):
                        ratio = 0.0  # กัน -0.0% เวลา 0 หารด้วยฐานติดลบ
                    set_cell(cell, {
                        "name": f"{float_repr(ratio, 1)}%",
                        "no_format": ratio,
                        "mode": None,  # ไม่ให้สี — สัดส่วนไม่ใช่ดี/แย่ในตัวมันเอง
                    })

    def _az_find_common_size_bases(self, options, lines, base_line_id, value_indexes):
        """ หายอดบรรทัดฐาน (เช่น รายได้รวม/สินทรัพย์รวม) แยกตาม column group """
        for line in lines:
            model, res_id = self._get_model_info_from_id(line["id"])
            if model == "account.report.line" and res_id == base_line_id:
                columns = line.get("columns") or []
                if len(columns) != len(options["columns"]):
                    continue
                return {
                    key: (columns[idx_map["balance"]].get("no_format")
                          if isinstance(columns[idx_map["balance"]], dict) else None)
                    for key, idx_map in value_indexes.items()
                    if "balance" in idx_map
                }
        # บรรทัดฐานไม่อยู่ในชุด lines (เคสกางบรรทัด groupby ผ่าน get_expanded_lines
        # ซึ่งส่งมาเฉพาะลูกที่กาง) — คำนวณยอดฐานจาก expression ของบรรทัดฐานตรง ๆ
        base_exprs = self.env["account.report.line"].browse(base_line_id).expression_ids.filtered(
            lambda e: e.label == "balance"
        )
        if not base_exprs:
            return {}
        totals = self._compute_expression_totals_for_each_column_group(
            base_exprs._expand_aggregations(), options,
        )
        return {
            key: (expr_totals.get(base_exprs[0]) or {}).get("value")
            for key, expr_totals in totals.items()
        }

    def _az_growth_percent_data(self, cur_value, prev_value, green_on_positive=True):
        # สูตรและการให้สีตามแนวเดียวกับ _compute_column_percent_comparison_data ของ Enterprise
        if not isinstance(prev_value, (int, float)) or float_is_zero(prev_value, precision_rounding=0.1):
            return {"name": _("n/a"), "no_format": None, "mode": "muted"}

        diff = cur_value - prev_value
        growth = round(diff / prev_value * 100, 1)
        if float_is_zero(growth, precision_digits=1):
            return {"name": "0.0%", "no_format": 0.0, "mode": "muted"}

        return {
            "name": f"{float_repr(growth, 1)}%",
            "no_format": growth,
            # เทียบกับฐานติดลบ สีต้องกลับทิศตาม green_on_positive เหมือน Enterprise
            "mode": "red" if ((diff > 0) ^ green_on_positive) else "green",
        }
