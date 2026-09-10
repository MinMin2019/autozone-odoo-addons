from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    # --- account routing -------------------------------------------------
    # Standard behaviour for a move into a production/inventory location
    # debits the Stock Output account (mrp_account: the WIP/production
    # account). For internal consumption we want the cost to land on the
    # product category's expense account (531xxx/532xxx per category),
    # exactly like the anglo-saxon COGS line of a customer invoice.
    #
    # NOTE: implemented on _get_accounting_data_for_valuation (the caller)
    # and not on _get_src_account/_get_dest_account, because mrp_account
    # overrides those without calling super() when the counterpart is a
    # production location, which would bypass this module depending on
    # module load order.

    def _get_accounting_data_for_valuation(self):
        journal_id, acc_src, acc_dest, acc_valuation = super()._get_accounting_data_for_valuation()
        expense = self.product_id.product_tmpl_id.get_product_accounts().get("expense")
        if expense:
            if self.location_dest_id.is_expense_consumption:
                acc_dest = expense.id
            if self.location_id.is_expense_consumption:
                # return from consumption (เบิกคืน): credit the same expense account
                acc_src = expense.id
        return journal_id, acc_src, acc_dest, acc_valuation

    # --- branch analytic on the expense line ------------------------------
    def _generate_valuation_lines_data(
        self, partner_id, qty, debit_value, credit_value,
        debit_account_id, credit_account_id, svl_id, description,
    ):
        rslt = super()._generate_valuation_lines_data(
            partner_id, qty, debit_value, credit_value,
            debit_account_id, credit_account_id, svl_id, description,
        )
        analytic = self.picking_type_id.consumption_analytic_account_id
        if analytic:
            distribution = {str(analytic.id): 100}
            if self.location_dest_id.is_expense_consumption:
                rslt["debit_line_vals"]["analytic_distribution"] = distribution
            elif self.location_id.is_expense_consumption:
                rslt["credit_line_vals"]["analytic_distribution"] = distribution
        return rslt
