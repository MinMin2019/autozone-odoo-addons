from odoo import api, fields, models

# ฟิลด์ที่ถูกใช้ใน domain_force ของ record rule
SCOPE_FIELDS = {"allowed_warehouse_ids", "warehouse_unrestricted"}


class ResUsers(models.Model):
    _inherit = "res.users"

    allowed_warehouse_ids = fields.Many2many(
        "stock.warehouse",
        "res_users_allowed_warehouse_rel", "user_id", "warehouse_id",
        string="Allowed Warehouses",
        help="Warehouses this user may see stock/operations for. "
             "Empty = all warehouses (not scoped yet).",
    )
    warehouse_unrestricted = fields.Boolean(
        string="See all warehouses",
        help="Bypass warehouse scoping (HQ / central-warehouse staff / admin).",
    )

    # ------------------------------------------------------------------ caching
    def _clear_rule_domain_cache(self):
        """สำคัญ: ir.rule._compute_domain ถูก ormcache ด้วยคีย์ (uid, model, mode)
        และ 'อบ' ค่า user.allowed_warehouse_ids ลงใน domain ที่ cache ไว้
        → เปลี่ยนคลังของ user แล้ว cache เดิมยังอยู่ = สิทธิ์ไม่เปลี่ยน
        ต้องล้าง cache ทุกครั้งที่ฟิลด์เหล่านี้เปลี่ยน"""
        registry = self.env.registry
        if hasattr(registry, "clear_cache"):
            registry.clear_cache()
        elif hasattr(registry, "clear_caches"):  # เผื่อเวอร์ชันเก่า
            registry.clear_caches()

    def write(self, vals):
        res = super().write(vals)
        if SCOPE_FIELDS & set(vals):
            self._clear_rule_domain_cache()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        if any(SCOPE_FIELDS & set(vals) for vals in vals_list):
            self._clear_rule_domain_cache()
        return users
