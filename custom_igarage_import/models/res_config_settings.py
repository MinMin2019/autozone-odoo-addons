from odoo import _, fields, models

P = "custom_igarage_import."


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    az_igarage_host = fields.Char("iGarage: Host", config_parameter=P + "igarage_host")
    az_igarage_port = fields.Char("iGarage: Port", config_parameter=P + "igarage_port", default="3306")
    az_igarage_db = fields.Char("iGarage: ฐานข้อมูล", config_parameter=P + "igarage_db")
    az_igarage_user = fields.Char("iGarage: ผู้ใช้", config_parameter=P + "igarage_user")
    az_igarage_password = fields.Char("iGarage: รหัสผ่าน", config_parameter=P + "igarage_password")
    az_autopart_server = fields.Char("AutoPart: Server", config_parameter=P + "autopart_server")
    az_autopart_port = fields.Char("AutoPart: Port", config_parameter=P + "autopart_port", default="1433")
    az_autopart_db = fields.Char("AutoPart: ฐานข้อมูล", config_parameter=P + "autopart_db", default="AutoPartNew")
    az_autopart_user = fields.Char("AutoPart: ผู้ใช้", config_parameter=P + "autopart_user")
    az_autopart_password = fields.Char("AutoPart: รหัสผ่าน", config_parameter=P + "autopart_password")
    az_autopart_driver = fields.Char("AutoPart: ODBC Driver", config_parameter=P + "autopart_driver", default="SQL Server")

    def _notify(self, ok, msg):
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("ทดสอบการเชื่อมต่อ"), "message": msg, "type": "success" if ok else "danger", "sticky": not ok}}

    def action_test_igarage(self):
        self.ensure_one()
        self.set_values()
        conn = self.env["az.igarage.connector"].igarage_connect()
        try:
            cur = conn.cursor()
            cur.execute("select count(*), max(date) from delivery_orders")
            n, last = cur.fetchone()
        finally:
            conn.close()
        return self._notify(True, _("เชื่อมต่อ iGarage สำเร็จ — ใบส่งของ %s ใบ ล่าสุดวันที่ %s") % (n, last))

    def action_test_autopart(self):
        self.ensure_one()
        self.set_values()
        conn = self.env["az.igarage.connector"].autopart_connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), MAX(StockCardDate) FROM ConsumableStockcard WHERE StockType='N'")
            n, last = cur.fetchone()
        finally:
            conn.close()
        return self._notify(True, _("เชื่อมต่อ AutoPart สำเร็จ — การ์ดสต็อก %s แถว ล่าสุดวันที่ %s") % (n, last))
