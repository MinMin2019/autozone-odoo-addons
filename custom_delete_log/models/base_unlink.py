import json
import logging

from odoo import fields, models
from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG

_logger = logging.getLogger(__name__)

# ห้ามเก็บ log ของตัวระบบ log เอง ไม่งั้นวนลูป/ลบ log ไม่ได้
EXCLUDED_MODELS = {"record.delete.log", "record.delete.rule"}


class Base(models.AbstractModel):
    _inherit = "base"

    def unlink(self):
        try:
            self._log_deletion_snapshot()
        except Exception:
            # การเก็บ log ต้องไม่ทำให้การลบตามปกติล้มเหลว
            _logger.exception("custom_delete_log: failed to log deletion of %s", self._name)
        return super().unlink()

    def write(self, vals):
        if "active" in vals and "active" in self._fields:
            try:
                self._log_archive_change(bool(vals["active"]))
            except Exception:
                _logger.exception("custom_delete_log: failed to log archive of %s", self._name)
        return super().write(vals)

    def _is_audit_tracked(self):
        if (
            not self
            or self._transient
            or self._name in EXCLUDED_MODELS
            or self.env.context.get(MODULE_UNINSTALL_FLAG)
            or "record.delete.rule" not in self.env
        ):
            return False
        return self._name in self.env["record.delete.rule"].sudo()._tracked_models()

    def _log_archive_change(self, new_active):
        if not self._is_audit_tracked():
            return
        changed = self.filtered(lambda rec: bool(rec.active) != new_active)
        if not changed:
            return
        model_desc = self.env["ir.model"]._get(self._name).name
        now = fields.Datetime.now()
        # savepoint: insert พัง (เช่น schema ยังเก่าระหว่างรอ upgrade โมดูลนี้)
        # ต้อง rollback เฉพาะส่วน log ไม่พา transaction หลักพัง
        with self.env.cr.savepoint():
            self._create_archive_logs(changed, new_active, model_desc, now)

    def _create_archive_logs(self, changed, new_active, model_desc, now):
        self.env["record.delete.log"].sudo().create(
            [
                {
                    "model_name": self._name,
                    "model_desc": model_desc,
                    "action": "unarchive" if new_active else "archive",
                    "res_id": rec.id,
                    "record_name": rec.display_name or "",
                    "user_id": self.env.uid,
                    "user_name": self.env.user.name,
                    "delete_date": now,
                }
                for rec in changed
            ]
        )

    def _log_deletion_snapshot(self):
        if not self._is_audit_tracked():
            return

        field_names = [
            name
            for name, field in self._fields.items()
            if field.store and field.type not in ("binary", "image", "one2many", "many2many")
        ]
        names = {rec.id: rec.display_name for rec in self}
        model_desc = self.env["ir.model"]._get(self._name).name
        now = fields.Datetime.now()
        with self.env.cr.savepoint():
            self._create_deletion_logs(field_names, names, model_desc, now)

    def _create_deletion_logs(self, field_names, names, model_desc, now):
        self.env["record.delete.log"].sudo().create(
            [
                {
                    "model_name": self._name,
                    "model_desc": model_desc,
                    "res_id": values["id"],
                    "record_name": names.get(values["id"]) or "",
                    "user_id": self.env.uid,
                    "user_name": self.env.user.name,
                    "delete_date": now,
                    "data_json": json.dumps(
                        values, default=str, ensure_ascii=False, indent=2
                    ),
                }
                for values in self.read(field_names)
            ]
        )
