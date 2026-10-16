def mark_uncoded_categories_skipped(env):
    """Leaf categories without a SKU code at install/upgrade time are taken as 'no SKU on purpose',
    so SKU managers are not flooded with 'set a category code' activities. Setting a code later
    clears the flag."""
    env.cr.execute("""
        UPDATE product_category c SET az_sku_skip = true
         WHERE c.az_sku_code IS NULL AND NOT COALESCE(c.az_sku_skip, false)
           AND NOT EXISTS (SELECT 1 FROM product_category k WHERE k.parent_id = c.id)
    """)
    return env.cr.rowcount


def post_init_hook(env):
    mark_uncoded_categories_skipped(env)
