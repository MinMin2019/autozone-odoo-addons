import base64
import json

from odoo import _, fields, models
from odoo.exceptions import UserError

FORMAT = "arb.roles.v1"


class AccessRoleExport(models.TransientModel):
    """Wizard: export role ทั้งชุดเป็น JSON — ใช้ย้าย dev → production
    จับคู่ catalog ด้วย (app, section, name) จึงไม่ผูกกับ id ของฐานต้นทาง"""
    _name = "access.role.export"
    _description = "Export Roles to JSON"

    role_ids = fields.Many2many(
        "access.role", string="Roles to export",
        default=lambda self: self.env["access.role"].search([]),
    )
    file = fields.Binary(string="File", readonly=True)
    filename = fields.Char(string="Filename")

    def action_export(self):
        self.ensure_one()
        if not self.role_ids:
            raise UserError(_("Select at least one role"))
        roles = []
        for role in self.role_ids:
            roles.append({
                "name": role.name,
                "code": role.code or "",
                "description": role.description or "",
                "include_foundation": role.include_foundation,
                "exclusive_membership": role.exclusive_membership,
                "users": role.user_ids.mapped("login"),
                "lines": [{
                    "app": line.catalog_id.app or "",
                    "section": line.catalog_id.section or "",
                    "name": line.catalog_id.name,
                    "level": line.level,
                    "domain": line.domain or "",
                } for line in role.line_ids],
            })
        payload = {
            "format": FORMAT,
            "exported_from": self.env.cr.dbname,
            "roles": roles,
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2)
        self.file = base64.b64encode(data.encode("utf-8"))
        self.filename = "access_roles_%s.json" % fields.Date.context_today(self)
        return {
            "type": "ir.actions.act_window",
            "name": _("Export Roles"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class AccessRoleImport(models.TransientModel):
    """Wizard: import role จากไฟล์ JSON (คู่กับ Export Roles)
    - จับคู่ role เดิมด้วย code (ถ้าไม่มี code ใช้ชื่อ) → อัปเดตทับ ไม่สร้างซ้ำ
    - บรรทัดสิทธิ์ถูกแทนที่ทั้งชุดตามไฟล์ (sync)
    - catalog/user ที่หาไม่เจอ = ข้าม + รายงานใน summary (ไม่ล้มทั้ง import)
    - ไม่ Apply อัตโนมัติ — admin ตรวจแล้วกด Apply เองทีละ role"""
    _name = "access.role.import"
    _description = "Import Roles from JSON"

    file = fields.Binary(string="File", required=True)
    filename = fields.Char(string="Filename")
    attach_users = fields.Boolean(
        string="Attach users (match by login)", default=True,
        help="Link users found by login to each role; missing logins are reported, not created",
    )
    summary = fields.Text(string="Result", readonly=True)

    def _find_catalog(self, app, section, name):
        Cat = self.env["access.catalog"]
        rec = Cat.search([
            ("app", "=", app), ("section", "=", section), ("name", "=", name),
        ], limit=1)
        if not rec:
            # เผื่อ entry ถูก archive ไว้ — ยังจับคู่ให้ (ดีกว่าหลุดหาย)
            rec = Cat.with_context(active_test=False).search([
                ("app", "=", app), ("section", "=", section), ("name", "=", name),
            ], limit=1)
        return rec

    def action_import(self):
        self.ensure_one()
        try:
            payload = json.loads(base64.b64decode(self.file).decode("utf-8"))
        except Exception:  # noqa: BLE001
            raise UserError(_("Cannot read the file — expected JSON from 'Export Roles'"))
        if payload.get("format") != FORMAT:
            raise UserError(_("Unknown file format — expected %s") % FORMAT)

        Role = self.env["access.role"]
        Line = self.env["access.role.line"]
        Users = self.env["res.users"]
        report = []
        for data in payload.get("roles", []):
            code = (data.get("code") or "").strip()
            name = (data.get("name") or "").strip()
            if not name:
                continue
            role = False
            if code:
                role = Role.with_context(active_test=False).search(
                    [("code", "=", code)], limit=1)
            if not role:
                role = Role.with_context(active_test=False).search(
                    [("name", "=", name)], limit=1)
            vals = {
                "name": name,
                "code": code or False,
                "description": data.get("description") or False,
                "include_foundation": bool(data.get("include_foundation", True)),
                "exclusive_membership": bool(data.get("exclusive_membership")),
            }
            created = not role
            if role:
                role.write(vals)
            else:
                role = Role.create(vals)

            # แทนที่บรรทัดทั้งชุดตามไฟล์
            role.line_ids.unlink()
            missing_cat = []
            added = 0
            for ln in data.get("lines", []):
                cat = self._find_catalog(
                    ln.get("app") or "", ln.get("section") or "", ln.get("name") or "")
                if not cat:
                    missing_cat.append("%s / %s / %s" % (
                        ln.get("app"), ln.get("section"), ln.get("name")))
                    continue
                Line.create({
                    "role_id": role.id,
                    "catalog_id": cat.id,
                    "level": ln.get("level") or "read",
                    "domain": ln.get("domain") or False,
                })
                added += 1

            missing_users = []
            if self.attach_users:
                logins = data.get("users") or []
                found = Users.search([("login", "in", logins)]) if logins else Users
                missing_users = sorted(set(logins) - set(found.mapped("login")))
                role.user_ids = [(6, 0, found.ids)] if logins else [(5, 0, 0)]

            msg = "%s role '%s': %s line(s)" % (
                "CREATED" if created else "UPDATED", role.name, added)
            if missing_cat:
                msg += "\n  !! catalog not found (skipped): " + "; ".join(missing_cat)
            if missing_users:
                msg += "\n  !! user login not found (skipped): " + ", ".join(missing_users)
            report.append(msg)

        report.append(_("Done — review each role, then press Apply to activate."))
        self.summary = "\n".join(report)
        return {
            "type": "ir.actions.act_window",
            "name": _("Import Roles"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
