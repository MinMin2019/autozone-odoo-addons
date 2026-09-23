def migrate(cr, version):
    # existing installs: classification fields (az_*) on products are editable without approval
    cr.execute("""
        UPDATE az_approval_type t
           SET free_field_prefixes = 'az_'
          FROM ir_model m
         WHERE m.id = t.model_id
           AND m.model = 'product.template'
           AND COALESCE(t.free_field_prefixes, '') = ''
    """)
