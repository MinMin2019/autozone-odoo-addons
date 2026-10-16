from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression

POSITIVE = ("=", "ilike", "=ilike", "like", "=like")


class ProductProduct(models.Model):
    _inherit = "product.product"

    az_sku = fields.Char(related="product_tmpl_id.az_sku", string="SKU")
    az_is_dummy = fields.Boolean(related="product_tmpl_id.az_is_dummy", string="สินค้าดัมมี่")

    @api.constrains("barcode")
    def _check_barcode_not_sku(self):
        for product in self.filtered("barcode"):
            clash = self.env["product.template"].with_context(active_test=False).search(
                [("az_sku", "=", product.barcode)], limit=1)
            if clash:
                raise ValidationError(f"บาร์โค้ด {product.barcode} ตรงกับ SKU ของสินค้า {clash.display_name}")

    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        if operator not in expression.NEGATIVE_TERM_OPERATORS and isinstance(value, str) and value:
            domain = expression.OR([domain, [("product_tmpl_id.az_sku", operator, value)]])
        return domain

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        # typed/scanned SKU in a product field (PO line, transfer, ...) -> exact hit first
        if name and operator in POSITIVE:
            products = self.search_fetch(
                expression.AND([args or [], [("product_tmpl_id.az_sku", "=", name.strip())]]),
                ["display_name"], limit=limit)
            if products:
                return [(p.id, p.display_name) for p in products.sudo()]
        return super().name_search(name, args, operator, limit)
