from odoo import models


class ThaiTaxReport(models.AbstractModel):
    _inherit = "report.l10n_th_account_tax_report.report_thai_tax"

    def _query_select_sub_tax(self):
        # Doc Ref. = เลขเอกสารภายในเสมอ: ใบ cash basis ใช้เลขบิลต้นทาง
        # แทน m.ref เดิมซึ่งเป็นข้อความอิสระที่พิมพ์ในช่อง Reference
        return """t.id, t.company_id, ml.account_id, t.partner_id,
            CASE WHEN ml.parent_state = 'posted' AND t.reversing_id IS NULL
                THEN t.tax_invoice_number
            ELSE
                t.tax_invoice_number || ' (VOID)'
            END AS tax_invoice_number,
            t.tax_invoice_date AS tax_date,
            CASE WHEN ml.parent_state = 'posted' AND t.reversing_id IS NULL
                THEN t.tax_base_amount
            ELSE 0.0
            END AS tax_base_amount,
            CASE WHEN ml.parent_state = 'posted' AND t.reversing_id IS NULL
                THEN t.balance
            ELSE 0.0
            END AS tax_amount,
            CASE WHEN m.tax_cash_basis_origin_move_id IS NOT NULL
                THEN (
                    SELECT om.name FROM account_move om
                    WHERE om.id = m.tax_cash_basis_origin_move_id
                )
            ELSE ml.move_name
            END AS name
        """

    def _query_select_tax(self):
        return """
            ROW_NUMBER() OVER (
                ORDER BY a.tax_date, a.tax_invoice_number, a.name
            ) AS row_number,
            a.company_id,
            a.account_id,
            a.partner_id,
            a.tax_invoice_number,
            TO_CHAR(a.tax_date, 'DD/MM/YYYY') AS tax_date,
            a.name,
            sum(a.tax_base_amount) AS tax_base_amount,
            sum(a.tax_amount) AS tax_amount
        """

    def _get_tax_data(self, tax_id, date_from, date_to, show_cancel, company_id):
        domain = self._domain_where_clause_tax(show_cancel)
        self._cr.execute(
            f"""
            SELECT {self._query_select_tax()}
            FROM (
                SELECT {self._query_select_sub_tax()}
                FROM account_move_tax_invoice t
                JOIN account_move_line ml ON ml.id = t.move_line_id
                JOIN account_move m ON m.id = ml.move_id
                WHERE {domain}
                    AND t.tax_invoice_number IS NOT NULL
                    AND ml.account_id IN (
                        SELECT account_id
                        FROM account_tax_repartition_line
                        WHERE account_id IS NOT NULL
                          AND tax_id = %s
                        GROUP BY account_id
                    )
                    AND (
                        (t.report_date >= %s AND t.report_date <= %s)
                        OR (
                            t.report_late_mo != '0'
                            AND EXTRACT(MONTH FROM t.report_date) <= %s
                            AND EXTRACT(YEAR FROM t.report_date) <= %s
                            AND EXTRACT(MONTH FROM t.report_date) >= %s
                            AND EXTRACT(YEAR FROM t.report_date) >= %s
                        )
                    )
                    AND ml.company_id = %s
                    AND t.reversed_id IS NULL
            ) a
            GROUP BY
                a.company_id,
                a.account_id,
                a.partner_id,
                a.tax_invoice_number,
                a.tax_date,
                a.name
            ORDER BY a.tax_date, a.tax_invoice_number, a.name
        """,
            (
                tax_id,
                date_from,
                date_to,
                date_to.month,
                date_to.year,
                date_from.month,
                date_from.year,
                company_id,
            ),
        )
        return self._cr.dictfetchall()