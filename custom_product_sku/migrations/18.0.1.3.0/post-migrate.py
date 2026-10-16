from odoo import SUPERUSER_ID, api

from odoo.addons.custom_product_sku.hooks import mark_uncoded_categories_skipped


def migrate(cr, version):
    mark_uncoded_categories_skipped(api.Environment(cr, SUPERUSER_ID, {}))
