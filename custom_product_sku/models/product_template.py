import re
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression

NO_BRAND = "000"
# writes to these fields may make a product eligible for a SKU
ISSUE_TRIGGERS = {"categ_id", "az_brand_id", "az_is_dummy", "active", "az_sku_exclude"}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    az_sku = fields.Char(
        "SKU", copy=False, readonly=True, index=True, tracking=True,
        help="หมวด 4 หลัก + แบรนด์ 3 หลัก + ลำดับ 4 หลัก — ระบบออกให้เองและล็อกไว้ "
             "ย้ายหมวด/เปลี่ยนแบรนด์ภายหลัง SKU ไม่เปลี่ยน (ผู้ดูแลรหัสกด 'ออกรหัสใหม่' ได้)")
    az_is_dummy = fields.Boolean(
        "สินค้าดัมมี่", tracking=True,
        help="สินค้าไม่ระบุยี่ห้อ เปิดไว้ซื้อแบบระบุสเป็ค/ขนาดในบรรทัด PO — ได้ลำดับ 9001 ขึ้นไป")
    az_sku_exclude = fields.Boolean(
        "ไม่ออก SKU", tracking=True,
        help="ติ๊กไว้ = สินค้าตัวนี้ไม่ต้องมี SKU แม้หมวดจะมีรหัส (เช่น ขนมในหมวดค่ารับรอง) "
             "เอาติ๊กออกเมื่อไร ระบบออก SKU ให้ทันที")
    az_sku_label_printed = fields.Boolean(
        "พิมพ์ฉลาก SKU แล้ว", copy=False, tracking=True,
        help="ติ๊กเมื่อพิมพ์ฉลากติดของแล้ว — ถ้าออกรหัสใหม่ต้องพิมพ์ฉลากใหม่")
    az_sku_history_ids = fields.One2many("az.sku.history", "product_tmpl_id", "ประวัติ SKU", readonly=True)
    az_sku_pending_reason = fields.Char("เหตุที่ยังไม่มี SKU", compute="_compute_az_sku_pending_reason")

    _sql_constraints = [
        ("az_sku_uniq", "unique(az_sku)", "SKU ซ้ำกับสินค้าอื่น"),
    ]

    # ------------------------------------------------------------------ helpers
    def _az_sku_prefix(self):
        """(prefix, reason): 7-digit category+brand code, or why it cannot be built."""
        self.ensure_one()
        if self.az_sku_exclude:
            return False, "ติ๊ก 'ไม่ออก SKU' ไว้ — สินค้าตัวนี้ไม่มี SKU"
        categ_code = self.categ_id.az_sku_code
        if not categ_code:
            subs = self.env["product.category"].sudo().search(
                [("id", "child_of", self.categ_id.id), ("id", "!=", self.categ_id.id), ("az_sku_code", "!=", False)],
                limit=6) if self.categ_id else self.env["product.category"]
            if subs:
                # a parent category was picked: point to the sub-categories that do get a SKU
                return False, ("เลือกหมวดย่อย เช่น %s แล้วระบบจะออก SKU ให้"
                               % " / ".join(subs[:5].mapped("name")))
            return False, f"หมวด {self.categ_id.complete_name or '-'} ไม่มีรหัสหมวด SKU (หมวดนี้ไม่ออก SKU)"
        brand = self.az_brand_id
        if brand and not (brand.code or "").strip():
            return False, (f"แบรนด์ {brand.name} ยังไม่มีรหัส — ให้ผู้ดูแลค่าจัดกลุ่มใส่รหัสแบรนด์ "
                           "แล้วระบบจะออก SKU ให้เอง")
        return categ_code + (brand.code.strip() if brand else NO_BRAND), False

    @api.depends("az_sku", "az_sku_exclude", "categ_id.az_sku_code", "az_brand_id.code")
    def _compute_az_sku_pending_reason(self):
        for tmpl in self:
            tmpl.az_sku_pending_reason = False if tmpl.az_sku else tmpl._az_sku_prefix()[1]

    def _az_issue_sku(self, reason=None):
        """Give a SKU to every active product here that has none and whose prefix can be built."""
        Seq = self.env["az.sku.sequence"].sudo()
        History = self.env["az.sku.history"].sudo()
        issued = self.browse()
        for tmpl in self:
            if tmpl.az_sku or not tmpl.active:
                continue
            prefix, _why = tmpl._az_sku_prefix()
            if not prefix:
                continue
            sku = Seq._next_sku(prefix, tmpl.az_is_dummy)
            tmpl.with_context(az_sku_write=True).write({"az_sku": sku})
            History.create({"sku": sku, "product_tmpl_id": tmpl.id, "product_name": tmpl.name,
                            "action": "issue", "reason": reason})
            issued |= tmpl
        return issued

    def _az_issue_sku_sorted(self, reason=None):
        """Issue SKUs in the review-draft order: inside each category+brand, normal products
        by old code then name, dummy products by name."""
        rows = []
        for tmpl in self.filtered(lambda t: not t.az_sku and t.active):
            prefix, _why = tmpl._az_sku_prefix()
            if prefix:
                if tmpl.az_is_dummy:
                    order = (tmpl.name or "", "")
                else:
                    order = ((tmpl.default_code or "").strip().upper(), tmpl.name or "")
                rows.append(((prefix, tmpl.az_is_dummy), order, tmpl.id, tmpl))
        rows.sort(key=lambda r: r[:3])
        issued = self.browse()
        for row in rows:
            issued |= row[3]._az_issue_sku(reason)
        return issued

    @api.model
    def _az_sku_generate_all(self, reason="เจน SKU ครั้งแรก"):
        """Initial run: SKU for every active product lacking one whose category has a code."""
        todo = self.search([("az_sku", "=", False), ("az_sku_exclude", "=", False),
                            ("categ_id.az_sku_code", "!=", False)])
        return todo._az_issue_sku_sorted(reason)

    def _az_sku_retire(self, action, reason, exclude=False):
        """Take the SKU off (kept in history, never reused). exclude=True also ticks 'ไม่ออก SKU'
        so the product does not get a new one on its next save."""
        self.ensure_one()
        old = self.az_sku
        if old:
            self.env["az.sku.history"].sudo().create({
                "sku": old, "product_tmpl_id": self.id, "product_name": self.name, "action": action,
                "reason": reason, "label_printed": self.az_sku_label_printed})
        vals = {"az_sku": False, "az_sku_label_printed": False}
        if exclude:
            vals["az_sku_exclude"] = True
        self.with_context(az_sku_write=True).write(vals)
        return old

    # ------------------------------------------------------------------ ORM
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("az_sku_write"):
            for vals in vals_list:
                vals.pop("az_sku", None)
                vals.pop("az_sku_label_printed", None)
        templates = super().create(vals_list)
        templates._az_issue_sku()
        templates._az_sku_check_categories()
        return templates

    def write(self, vals):
        if "az_sku" in vals and not self.env.context.get("az_sku_write"):
            raise UserError("แก้ SKU เองไม่ได้ — ระบบออกให้อัตโนมัติ "
                            "ถ้าต้องเปลี่ยนให้ผู้ดูแลรหัสสินค้ากด 'ออกรหัสใหม่' หรือ 'ยกเลิก SKU'")
        if vals.get("az_sku_exclude") and not self.env.context.get("az_sku_write") \
                and self.filtered("az_sku"):
            raise UserError("สินค้านี้มี SKU แล้ว — ถ้าไม่ต้องการ SKU ให้ผู้ดูแลรหัสสินค้ากดปุ่ม 'ยกเลิก SKU'")
        res = super().write(vals)
        if not self.env.context.get("az_sku_write") and ISSUE_TRIGGERS & set(vals):
            self.filtered(lambda t: not t.az_sku)._az_issue_sku()
            self._az_sku_check_categories()
        return res

    def _az_sku_check_categories(self):
        """A product without SKU landed in a category that has no code yet -> remind SKU managers."""
        cats = self.filtered(lambda t: t.active and not t.az_sku and not t.az_sku_exclude).categ_id
        if cats:
            cats._az_sku_notify_missing_code()

    @api.constrains("az_sku")
    def _check_az_sku(self):
        for tmpl in self.filtered("az_sku"):
            if not re.fullmatch(r"\d{11}", tmpl.az_sku):
                raise ValidationError(f"SKU ต้องเป็นตัวเลข 11 หลัก ({tmpl.az_sku})")
            clash = self.env["product.product"].with_context(active_test=False).search(
                [("barcode", "=", tmpl.az_sku)], limit=1)
            if clash:
                raise ValidationError(f"SKU {tmpl.az_sku} ตรงกับบาร์โค้ดของสินค้า {clash.display_name}")

    # ------------------------------------------------------------------ search by SKU
    @api.model
    def _search_display_name(self, operator, value):
        domain = super()._search_display_name(operator, value)
        if operator not in expression.NEGATIVE_TERM_OPERATORS and isinstance(value, str) and value:
            domain = expression.OR([domain, [("az_sku", operator, value)]])
        return domain

    # ------------------------------------------------------------------ actions
    def _az_sku_wizard(self, mode, title):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "az.sku.reissue",
            "view_mode": "form",
            "target": "new",
            "context": {"default_product_tmpl_id": self.id, "default_mode": mode},
        }

    def action_az_sku_reissue(self):
        return self._az_sku_wizard("reissue", "ออกรหัส SKU ใหม่")

    def action_az_sku_cancel(self):
        return self._az_sku_wizard("cancel", "ยกเลิก SKU")
