"""ตัวเชื่อมต่อฐานภายนอก (อ่านอย่างเดียว) — ค่าเชื่อมต่อเก็บใน ir.config_parameter (ตั้งที่ Settings)"""
import os
import sys

from odoo import _, api, models
from odoo.exceptions import UserError

_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")

P = "custom_igarage_import."


class IgarageConnector(models.AbstractModel):
    _name = "az.igarage.connector"
    _description = "ตัวเชื่อมต่อ iGarage / AutoPart"

    @api.model
    def _param(self, key, default=""):
        return self.env["ir.config_parameter"].sudo().get_param(P + key, default) or default

    @api.model
    def igarage_connect(self):
        if _LIB not in sys.path:
            sys.path.insert(0, _LIB)
        import pymysql  # vendored (MIT) ใน lib/
        host = self._param("igarage_host")
        if not host:
            raise UserError(_("ยังไม่ได้ตั้งค่าการเชื่อมต่อ iGarage (Inventory > Configuration > Settings)"))
        try:
            return pymysql.connect(host=host, port=int(self._param("igarage_port", "3306")),
                                   user=self._param("igarage_user"), password=self._param("igarage_password"),
                                   database=self._param("igarage_db"), charset="utf8", connect_timeout=20, read_timeout=600)
        except Exception as e:  # noqa: BLE001
            raise UserError(_("เชื่อมต่อ iGarage ไม่สำเร็จ: %s") % e) from e

    @api.model
    def autopart_connect(self):
        try:
            import pyodbc
        except ImportError as e:
            raise UserError(_("เครื่องเซิร์ฟเวอร์ไม่มี pyodbc สำหรับต่อ AutoPart")) from e
        server = self._param("autopart_server")
        if not server:
            raise UserError(_("ยังไม่ได้ตั้งค่าการเชื่อมต่อ AutoPart (Inventory > Configuration > Settings)"))
        port = self._param("autopart_port", "1433")
        cs = "DRIVER={%s};SERVER=%s,%s;DATABASE=%s;UID=%s;PWD=%s" % (
            self._param("autopart_driver", "SQL Server"), server, port, self._param("autopart_db", "AutoPartNew"),
            self._param("autopart_user"), self._param("autopart_password"))
        try:
            return pyodbc.connect(cs, timeout=20, readonly=True)
        except Exception as e:  # noqa: BLE001
            raise UserError(_("เชื่อมต่อ AutoPart ไม่สำเร็จ: %s") % e) from e
