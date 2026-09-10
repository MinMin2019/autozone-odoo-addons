import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# เก็บ log สรุปการเข้าเมนูย้อนหลังกี่วัน (ลบทิ้งโดย autovacuum รายวันของ Odoo)
RETENTION_DAYS = 365


class MenuUsageLog(models.Model):
    _name = "menu.usage.log"
    _description = "Menu Usage Log (daily summary)"
    _order = "date desc, visit_count desc, id desc"

    date = fields.Date(string="Date", required=True, index=True)
    user_id = fields.Many2one("res.users", string="User", ondelete="set null", index=True)
    menu_id = fields.Many2one("ir.ui.menu", string="Menu", ondelete="set null")
    menu_path = fields.Char(string="Menu Path")
    action_ref = fields.Char(string="Action Ref", required=True)
    action_name = fields.Char(string="Action Name")
    visit_count = fields.Integer(string="Visits", default=1)

    _sql_constraints = [
        (
            "date_user_action_uniq",
            "unique(date, user_id, action_ref)",
            "Menu usage is aggregated per user, menu and day.",
        ),
    ]

    def _log_action_load(self, action):
        """บันทึกการเปิด action จากเมนู (เรียกจาก controller /web/action/load)

        request หลักเป็น readonly cursor เขียนไม่ได้ ต้อง upsert ผ่าน cursor แยก
        และห้าม raise ไม่ว่ากรณีใด — log พังต้องไม่กระทบการเปิดหน้าจอ
        """
        try:
            action_id = action.get("id")
            action_type = action.get("type")
            if not action_id or not action_type:
                return
            action_ref = "%s,%s" % (action_type, action_id)
            # เก็บเฉพาะ action ที่ผูกกับเมนู — action ลอย ๆ (wizard/ลิงก์) ไม่นับ
            menu = (
                self.env["ir.ui.menu"]
                .sudo()
                .with_context(**{"ir.ui.menu.full_list": True})
                .search([("action", "=", action_ref)], order="id", limit=1)
            )
            if not menu:
                return
            day = fields.Datetime.context_timestamp(
                self.env.user, fields.Datetime.now()
            ).date()
            now = fields.Datetime.now()
            with self.pool.cursor() as cr:
                cr.execute(
                    """
                    INSERT INTO menu_usage_log
                        (date, user_id, menu_id, menu_path, action_ref, action_name,
                         visit_count, create_uid, create_date, write_uid, write_date)
                    VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s)
                    ON CONFLICT (date, user_id, action_ref)
                    DO UPDATE SET
                        visit_count = menu_usage_log.visit_count + 1,
                        menu_id = EXCLUDED.menu_id,
                        menu_path = EXCLUDED.menu_path,
                        write_date = EXCLUDED.write_date
                    """,
                    (
                        day,
                        self.env.uid,
                        menu.id,
                        (menu.complete_name or menu.name or "")[:512],
                        action_ref,
                        (action.get("name") or action.get("display_name") or "")[:256],
                        self.env.uid,
                        now,
                        self.env.uid,
                        now,
                    ),
                )
        except Exception:
            _logger.exception("custom_delete_log: failed to write menu usage log")

    @api.autovacuum
    def _gc_menu_usage_logs(self):
        cutoff = fields.Date.today() - timedelta(days=RETENTION_DAYS)
        self.sudo().search([("date", "<", cutoff)]).unlink()
