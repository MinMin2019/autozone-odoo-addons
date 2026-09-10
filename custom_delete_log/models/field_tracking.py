import logging

from markupsafe import Markup

from odoo import api, models

_logger = logging.getLogger(__name__)

# field อ่อนไหวที่ต้อง log ลง chatter เมื่อถูกแก้ (field ปกติ Odoo track ให้อยู่แล้ว
# แต่พวกนี้เป็น company-dependent/property field ซึ่ง tracking ของ Odoo ไม่รองรับ)
PARTNER_AUDIT_FIELDS = {
    "property_payment_term_id": "เงื่อนไขชำระเงิน (ลูกค้า)",
    "property_supplier_payment_term_id": "เงื่อนไขชำระเงิน (ผู้ขาย)",
    "credit_limit": "วงเงินเครดิต",
}

PRODUCT_AUDIT_FIELDS = {
    "list_price": "ราคาขาย",
    "standard_price": "ต้นทุน",
}


def _display(value):
    if isinstance(value, models.BaseModel):
        return value.display_name or "-"
    if value in (False, None, ""):
        return "-"
    return str(value)


def _log_changes_to_chatter(records, vals, audit_fields, post_on=None):
    """เทียบค่าก่อน/หลัง write แล้ว post ลง chatter — คืนค่า snapshot ก่อนแก้"""
    tracked = {f: label for f, label in audit_fields.items() if f in vals and f in records._fields}
    if not tracked:
        return None
    return {rec.id: {f: rec[f] for f in tracked} for rec in records}, tracked


def _post_changes(records, old_values, tracked, post_on=None):
    for rec in records:
        changes = []
        for fname, label in tracked.items():
            old = old_values.get(rec.id, {}).get(fname)
            new = rec[fname]
            if old != new:
                # Markup % จะ escape ค่าให้เอง ส่วน <br/> คงเป็น html จริง
                changes.append(Markup("%s: %s → %s") % (label, _display(old), _display(new)))
        if changes:
            target = post_on(rec) if post_on else rec
            if target:
                # savepoint กัน chatter พังแล้วลาก transaction หลักพังตาม
                with records.env.cr.savepoint():
                    target.message_post(body=Markup("แก้ไขข้อมูลสำคัญ<br/>") + Markup("<br/>").join(changes))


class ResPartner(models.Model):
    _inherit = "res.partner"

    def write(self, vals):
        snapshot = None
        try:
            snapshot = _log_changes_to_chatter(self, vals, PARTNER_AUDIT_FIELDS)
        except Exception:
            _logger.exception("custom_delete_log: partner field audit failed (pre-write)")
        result = super().write(vals)
        if snapshot:
            try:
                _post_changes(self, snapshot[0], snapshot[1])
            except Exception:
                _logger.exception("custom_delete_log: partner field audit failed (post-write)")
        return result


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def write(self, vals):
        snapshot = None
        try:
            snapshot = _log_changes_to_chatter(self, vals, PRODUCT_AUDIT_FIELDS)
        except Exception:
            _logger.exception("custom_delete_log: product field audit failed (pre-write)")
        result = super().write(vals)
        if snapshot:
            try:
                _post_changes(self, snapshot[0], snapshot[1])
            except Exception:
                _logger.exception("custom_delete_log: product field audit failed (post-write)")
        return result


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    def _audit_describe(self):
        self.ensure_one()
        parts = [self.acc_number or "-"]
        if self.bank_id:
            parts.append(self.bank_id.display_name)
        return " / ".join(parts)

    def _audit_post(self, partner, body):
        try:
            if partner:
                with self.env.cr.savepoint():
                    partner.message_post(body=body)
        except Exception:
            _logger.exception("custom_delete_log: bank account audit failed")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._audit_post(rec.partner_id, Markup("เพิ่มบัญชีธนาคาร: %s") % rec._audit_describe())
        return records

    def write(self, vals):
        watched = {"acc_number", "bank_id", "partner_id", "acc_holder_name"} & vals.keys()
        old_data = {}
        if watched:
            old_data = {
                rec.id: (rec._audit_describe(), rec.partner_id) for rec in self
            }
        result = super().write(vals)
        for rec in self:
            if rec.id not in old_data:
                continue
            old_desc, old_partner = old_data[rec.id]
            new_desc = rec._audit_describe()
            if old_desc != new_desc or old_partner != rec.partner_id:
                body = Markup("แก้ไขบัญชีธนาคาร: %s → %s") % (old_desc, new_desc)
                rec._audit_post(rec.partner_id, body)
                if old_partner != rec.partner_id:
                    rec._audit_post(old_partner, Markup("ย้ายบัญชีธนาคาร %s ไปผู้ติดต่ออื่น") % old_desc)
        return result

    def unlink(self):
        info = [(rec.partner_id, rec._audit_describe()) for rec in self]
        result = super().unlink()
        for partner, desc in info:
            self._audit_post(partner, Markup("ลบบัญชีธนาคาร: %s") % desc)
        return result
