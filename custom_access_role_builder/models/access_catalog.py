from odoo import api, fields, models


class AccessCatalog(models.Model):
    """แคตตาล็อกเมนู/เอกสาร — ตัวเลือกที่ผู้ดูแลหยิบมาต่อเป็น role
    seed จากไฟล์ data/master_matrix.csv (ดู hooks.py)"""
    _name = "access.catalog"
    _description = "Access Catalog (menu/document)"
    _order = "app, section, name"

    name = fields.Char(string="Menu / Document", required=True)
    app = fields.Char(string="App", index=True)
    section = fields.Char(string="Section (Main)")
    menu_path = fields.Char(
        string="Menu Path",
        help="Full menu path under the app (captured by Import), '/'-separated. "
             "Used to nest the My Work menu faithfully. Empty = use App/Section.",
    )

    model_id = fields.Many2one("ir.model", string="Data Model", ondelete="cascade")
    model_name = fields.Char(string="Model (technical)")

    action_id = fields.Many2one(
        "ir.actions.act_window", string="Existing Action", ondelete="set null",
        help="Point to a custom module's existing action to reuse it as-is "
             "(keeps its context/views/defaults) instead of auto-generating one",
    )
    client_action_id = fields.Many2one(
        "ir.actions.client", string="Client Action", ondelete="set null",
        help="For screens that are client actions instead of window actions — "
             "e.g. Enterprise accounting reports (P&L, Balance Sheet, Tax Report). "
             "Takes precedence over Existing Action. Still set a Data Model "
             "(e.g. account.report) so the role can grant read access",
    )
    extra_read_model_ids = fields.Many2many(
        "ir.model", "access_catalog_extra_read_rel", "catalog_id", "model_id",
        string="Extra Read Models",
        help="Extra models to grant READ when this entry is used — covers cross-model "
             "reads / smart buttons so the screen opens without AccessError",
    )
    view_mode = fields.Char(
        string="View Mode", default="list,form",
        help="View modes for the auto-generated action (e.g. 'kanban,list,form'). "
             "Ignored when Existing Action is set.",
    )

    needs_rule = fields.Boolean(
        string="Needs Record Rule",
        help="This menu shares its model with others; splitting requires ir.rule + domain",
    )
    domain = fields.Char(
        string="Domain (record rule)",
        help="Domain for ir.rule, e.g. [('move_type','=','in_invoice')] — leave empty if no split needed",
    )
    domain_hint = fields.Char(string="Domain hint (from CSV)", help="Original text before conversion to a domain")

    default_level = fields.Selection(
        selection=lambda self: self.env["access.role.line"]._level_selection(),
        string="Default Level",
        default="read",
    )
    note = fields.Char(string="Note")
    needs_review = fields.Boolean(
        string="Needs Review",
        help="Seeder could not resolve the model / needs verification — not usable until filled in",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("uniq_app_section_name", "unique(app, section, name)",
         "Duplicate catalog entry (same app/section/name)"),
    ]

    def name_get(self):
        res = []
        for rec in self:
            label = rec.name
            if rec.app:
                label = "%s · %s" % (rec.app, rec.name)
            res.append((rec.id, label))
        return res

    @api.onchange("model_id")
    def _onchange_model_id(self):
        for rec in self:
            rec.model_name = rec.model_id.model or False

    @api.onchange("action_id")
    def _onchange_action_id(self):
        """เลือก action เดิม → เติม model + domain ให้อัตโนมัติ"""
        for rec in self:
            if rec.action_id:
                model = self.env["ir.model"].search(
                    [("model", "=", rec.action_id.res_model)], limit=1)
                if model:
                    rec.model_id = model.id
                    rec.model_name = model.model
                if rec.action_id.domain and not rec.domain:
                    rec.domain = rec.action_id.domain

    @api.model
    def action_reload_from_csv(self):
        """Button: reload catalog from master_matrix.csv + custom_catalog.csv"""
        from ..hooks import seed_catalog, seed_custom_catalog
        n = seed_catalog(self.env)
        c = seed_custom_catalog(self.env)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Catalog reloaded",
                "message": "Master: %s entries · Custom-module: %s new entries" % (n, c),
                "type": "success",
                "sticky": False,
            },
        }
