import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ModuleChangeLog(models.Model):
    _name = "module.change.log"
    _description = "Module Install/Upgrade Log"
    _order = "create_date desc, id desc"

    module_name = fields.Char(string="Module", index=True)
    shortdesc = fields.Char(string="Description")
    old_state = fields.Char(string="From State")
    new_state = fields.Char(string="To State")
    latest_version = fields.Char(string="Version")
    user_id = fields.Many2one("res.users", string="By", ondelete="set null")
    user_name = fields.Char(string="By (name)")


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def write(self, vals):
        new_state = vals.get("state")
        if new_state and "module.change.log" in self.env:
            try:
                changed = self.filtered(lambda mod: mod.state != new_state)
                # savepoint: ถ้า insert พัง (เช่นตารางยังไม่ถูกสร้างตอนกำลัง upgrade
                # ตัวโมดูลนี้เอง) ให้ rollback เฉพาะส่วนนี้ ไม่พา transaction หลักพัง
                if changed:
                    with self.env.cr.savepoint():
                        self._create_module_change_logs(changed, new_state)
            except Exception:
                _logger.exception("custom_delete_log: failed to log module state change")
        return super().write(vals)

    def _create_module_change_logs(self, changed, new_state):
        self.env["module.change.log"].sudo().create(
            [
                {
                    "module_name": mod.name,
                    "shortdesc": mod.shortdesc,
                    "old_state": mod.state,
                    "new_state": new_state,
                    "latest_version": mod.latest_version,
                    "user_id": self.env.uid,
                    "user_name": self.env.user.name,
                }
                for mod in changed
            ]
        )
