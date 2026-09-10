import logging

from odoo import api, fields, models, SUPERUSER_ID
from odoo.exceptions import AccessDenied
from odoo.http import request

_logger = logging.getLogger(__name__)


class AuthLog(models.Model):
    _name = "auth.log"
    _description = "Login Log"
    _order = "create_date desc, id desc"

    login = fields.Char(string="Login", index=True)
    user_id = fields.Many2one("res.users", string="User", ondelete="set null")
    success = fields.Boolean(string="Success", index=True)
    ip = fields.Char(string="IP Address")
    user_agent = fields.Char(string="Browser / Device")


class ResUsers(models.Model):
    _inherit = "res.users"

    @classmethod
    def _login(cls, db, credential, user_agent_env):
        try:
            auth_info = super()._login(db, credential, user_agent_env)
        except AccessDenied:
            cls._create_auth_log(credential.get("login"), False, None)
            raise
        cls._create_auth_log(credential.get("login"), True, auth_info.get("uid"))
        return auth_info

    @classmethod
    def _create_auth_log(cls, login, success, uid):
        # เขียนด้วย cursor แยก เพราะ _login จัดการ transaction ของตัวเอง
        # (กรณี login fail transaction หลักถูก rollback แต่ log ต้องอยู่)
        try:
            ip = request.httprequest.environ.get("REMOTE_ADDR") if request else "n/a"
            user_agent = request.httprequest.user_agent.string if request else ""
            with cls.pool.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                if "auth.log" in env:
                    env["auth.log"].create(
                        {
                            "login": login and login[:128],
                            "success": success,
                            "user_id": uid,
                            "ip": ip,
                            "user_agent": user_agent and user_agent[:256],
                        }
                    )
        except Exception:
            _logger.exception("custom_delete_log: failed to write auth log")
