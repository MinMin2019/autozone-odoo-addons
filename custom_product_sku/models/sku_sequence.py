from odoo import api, fields, models
from odoo.exceptions import UserError

DUMMY_START = 9001
NORMAL_MAX = DUMMY_START - 1
DUMMY_MAX = 9999


class AzSkuSequence(models.Model):
    """Running number per category code + brand code, normal and dummy counted apart.

    The counter only moves forward, so a number is never handed out twice even
    after the product is archived, deleted or re-issued.
    """
    _name = "az.sku.sequence"
    _description = "ตัวนับลำดับ SKU"
    _order = "prefix, dummy"

    prefix = fields.Char("หมวด+แบรนด์", size=7, required=True, readonly=True)
    dummy = fields.Boolean("ดัมมี่", readonly=True)
    last_number = fields.Integer("เลขล่าสุด", readonly=True)

    _sql_constraints = [
        ("prefix_dummy_uniq", "unique(prefix, dummy)", "ตัวนับ SKU ซ้ำ"),
    ]

    @api.model
    def _max_used(self, prefix, dummy):
        """Highest running number already used under prefix (products incl. archived + history)."""
        self.env.cr.execute("""
            SELECT max(substr(sku, 8, 4)::int) FROM (
                SELECT az_sku AS sku FROM product_template WHERE az_sku LIKE %(p)s
                UNION ALL
                SELECT sku FROM az_sku_history WHERE sku LIKE %(p)s
            ) s
            WHERE sku ~ '^[0-9]{11}$'
              AND substr(sku, 8, 4)::int BETWEEN %(lo)s AND %(hi)s
        """, {"p": prefix + "%", "lo": DUMMY_START if dummy else 1, "hi": DUMMY_MAX if dummy else NORMAL_MAX})
        used = self.env.cr.fetchone()[0]
        return used or (DUMMY_START - 1 if dummy else 0)

    @api.model
    def _next_sku(self, prefix, dummy):
        cr = self.env.cr
        query = "SELECT id, last_number FROM az_sku_sequence WHERE prefix = %s AND dummy = %s FOR UPDATE"
        cr.execute(query, (prefix, dummy))
        row = cr.fetchone()
        if not row:
            cr.execute("""
                INSERT INTO az_sku_sequence (prefix, dummy, last_number, create_uid, write_uid, create_date, write_date)
                VALUES (%s, %s, %s, %s, %s, now() at time zone 'utc', now() at time zone 'utc')
                ON CONFLICT (prefix, dummy) DO NOTHING
            """, (prefix, dummy, self._max_used(prefix, dummy), self.env.uid, self.env.uid))
            cr.execute(query, (prefix, dummy))
            row = cr.fetchone()
        seq_id, last = row
        number = max(last, self._max_used(prefix, dummy)) + 1
        if number > (DUMMY_MAX if dummy else NORMAL_MAX):
            raise UserError(f"ลำดับ SKU ของหมวด+แบรนด์ {prefix} {'(ดัมมี่) ' if dummy else ''}เต็มแล้ว")
        cr.execute("UPDATE az_sku_sequence SET last_number = %s, write_uid = %s, "
                   "write_date = now() at time zone 'utc' WHERE id = %s", (number, self.env.uid, seq_id))
        self.invalidate_model(["last_number"])
        return prefix + str(number).zfill(4)
