import re

from odoo import api, models
from odoo.exceptions import ValidationError


class AzProductBrand(models.Model):
    _inherit = "az.product.brand"

    @api.constrains("code")
    def _check_sku_brand_code(self):
        for brand in self:
            if brand.code and not re.fullmatch(r"\d{3}", brand.code.strip()):
                raise ValidationError(f"รหัสแบรนด์ต้องเป็นตัวเลข 3 หลัก ใช้ประกอบ SKU ({brand.name})")

    def write(self, vals):
        res = super().write(vals)
        if vals.get("code") and not self.env.context.get("az_sku_no_auto"):
            # products waiting only for this brand code get their SKU now
            self.env["product.template"].search(
                [("az_brand_id", "in", self.ids), ("az_sku", "=", False)])._az_issue_sku_sorted()
        return res
