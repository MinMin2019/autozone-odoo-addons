import logging

from odoo.http import request, route
from odoo.addons.web.controllers.action import Action

_logger = logging.getLogger(__name__)


class ActionWithMenuUsageLog(Action):

    @route()
    def load(self, action_id, context=None):
        result = super().load(action_id, context=context)
        # load_breadcrumbs เรียก load ซ้ำตอน restore หน้า (refresh/กลับจากลิงก์)
        # ไม่ใช่การกดเมนูจริง — ข้ามไม่นับ
        if result and not getattr(request, "_az_skip_menu_usage_log", False):
            try:
                request.env["menu.usage.log"]._log_action_load(result)
            except Exception:
                _logger.exception("custom_delete_log: menu usage logging failed")
        return result

    @route()
    def load_breadcrumbs(self, actions):
        request._az_skip_menu_usage_log = True
        try:
            return super().load_breadcrumbs(actions)
        finally:
            request._az_skip_menu_usage_log = False
