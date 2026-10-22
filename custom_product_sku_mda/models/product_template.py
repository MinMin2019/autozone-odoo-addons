from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _az_sku_waits_approval(self):
        """Item approval is switched on and this product is not approved yet -> no SKU yet,
        so the approver can still fix category / brand before the number is fixed."""
        self.ensure_one()
        return bool(self.env["az.approval.type"]._get_for_model("product.template")) \
            and self.approval_state != "approved"

    def _az_sku_prefix(self):
        if self._az_sku_waits_approval():
            return False, "รออนุมัติไอเท็ม — ระบบจะออก SKU ให้เมื่อผู้อนุมัติกดอนุมัติ (ตามหมวด/แบรนด์ ณ ตอนนั้น)"
        return super()._az_sku_prefix()

    @api.depends("approval_state")
    def _compute_az_sku_pending_reason(self):
        return super()._compute_az_sku_pending_reason()

    def write(self, vals):
        res = super().write(vals)
        if vals.get("approval_state") == "approved":
            # issued on approval, with the category / brand the approver checked
            self.filtered(lambda t: not t.az_sku)._az_issue_sku(reason="ออก SKU ตอนอนุมัติไอเท็ม")
        return res
