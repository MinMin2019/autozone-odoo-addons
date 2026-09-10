from odoo import _, api, fields, models


class AccessRoleLineAdd(models.TransientModel):
    """Wizard: หยิบ catalog หลายรายการเข้า role ในคลิกเดียว
    (แทนการกด Add a line ทีละแถว)"""
    _name = "access.role.line.add"
    _description = "Add Multiple Catalog Entries to Role"

    role_id = fields.Many2one("access.role", required=True, ondelete="cascade")
    catalog_ids = fields.Many2many(
        "access.catalog", string="Menus / Documents",
        domain=[("needs_review", "=", False)],
    )
    # รายการที่ role นี้หยิบไปแล้ว — ใช้ซ่อนออกจากหน้าเลือก (domain ใน view)
    existing_catalog_ids = fields.Many2many(
        "access.catalog", "rel_arb_line_add_existing", compute="_compute_existing_catalog_ids",
        string="Already in this role",
    )

    @api.depends("role_id")
    def _compute_existing_catalog_ids(self):
        for wiz in self:
            wiz.existing_catalog_ids = wiz.role_id.line_ids.mapped("catalog_id")
    use_default_level = fields.Boolean(
        string="Use each entry's default level", default=True,
        help="Take the access level from each catalog entry's Default Level; "
             "untick to force one level for every selected entry",
    )
    level = fields.Selection(
        selection=lambda self: self.env["access.role.line"]._level_selection(),
        string="Access Level", default="read",
    )

    def action_add(self):
        self.ensure_one()
        Line = self.env["access.role.line"]
        existing = self.role_id.line_ids.mapped("catalog_id")
        added = 0
        for cat in self.catalog_ids - existing:
            level = cat.default_level if (self.use_default_level and cat.default_level) else self.level
            Line.create({
                "role_id": self.role_id.id,
                "catalog_id": cat.id,
                "level": level,
                # onchange ไม่ทำงานตอน create ด้วยโค้ด — ต้อง copy domain เอง
                # ไม่งั้น entry ที่ needs_rule จะไม่ได้ ir.rule (ข้อมูลไม่ถูก split)
                "domain": cat.domain or False,
            })
            added += 1
        skipped = len(self.catalog_ids) - added
        msg = _("Added %s line(s)") % added
        if skipped:
            msg += _(" · skipped %s already in this role") % skipped
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Lines added"),
                "message": msg,
                "type": "success", "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }
