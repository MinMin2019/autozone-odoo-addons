from odoo import api, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    @api.model_create_multi
    def create(self, vals_list):
        warehouses = super().create(vals_list)
        warehouses._create_consumption_picking_type()
        return warehouses

    def _create_consumption_picking_type(self):
        """Create the 'เบิกใช้วัสดุ' (CONS) operation type for each warehouse.

        Idempotent: warehouses that already have a CONS type are skipped.
        The branch analytic account is matched by code == warehouse code.
        """
        consumption_loc = self.env.ref(
            "custom_branch_consumption.location_consumption", raise_if_not_found=False
        )
        if not consumption_loc:
            return
        PickingType = self.env["stock.picking.type"]
        Analytic = self.env["account.analytic.account"]
        for wh in self:
            existing = PickingType.with_context(active_test=False).search(
                [("warehouse_id", "=", wh.id), ("sequence_code", "=", "CONS")], limit=1
            )
            if existing:
                continue
            analytic = Analytic.search(
                [
                    ("code", "=", wh.code),
                    ("company_id", "in", (wh.company_id.id, False)),
                ],
                limit=1,
            )
            picking_type = PickingType.create(
                {
                    "name": "เบิกใช้วัสดุ",
                    "code": "internal",
                    "sequence_code": "CONS",
                    "warehouse_id": wh.id,
                    "company_id": wh.company_id.id,
                    "default_location_src_id": wh.lot_stock_id.id,
                    "default_location_dest_id": consumption_loc.id,
                    "consumption_analytic_account_id": analytic.id,
                    "sequence": (wh.int_type_id.sequence or 0) + 1,
                }
            )
            # returns (เบิกคืน) keep the same operation type so the analytic
            # account is reversed on the same branch
            picking_type.return_picking_type_id = picking_type
