from odoo import api, fields, models, tools


class RecordDeleteLog(models.Model):
    _name = "record.delete.log"
    _description = "Record Deletion Log"
    _order = "delete_date desc, id desc"

    model_name = fields.Char(string="Model", required=True, index=True)
    model_desc = fields.Char(string="Model Description")
    action = fields.Selection(
        [("delete", "Delete"), ("archive", "Archive"), ("unarchive", "Unarchive")],
        string="Action",
        default="delete",
        required=True,
        index=True,
    )
    res_id = fields.Integer(string="Record ID", required=True)
    record_name = fields.Char(string="Record Name", index=True)
    user_id = fields.Many2one("res.users", string="Deleted By", ondelete="set null", index=True)
    user_name = fields.Char(string="Deleted By (name)")
    delete_date = fields.Datetime(string="Deleted On", default=fields.Datetime.now, index=True)
    data_json = fields.Text(string="Data Snapshot")


class RecordDeleteRule(models.Model):
    _name = "record.delete.rule"
    _description = "Deletion Log Tracked Model"
    _rec_name = "model_name"

    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
        domain=[("transient", "=", False)],
    )
    model_name = fields.Char(
        string="Technical Name", related="model_id.model", store=True, index=True
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("model_uniq", "unique(model_id)", "This model is already tracked."),
    ]

    @api.model
    @tools.ormcache()
    def _tracked_models(self):
        self.env.cr.execute("SELECT model_name FROM record_delete_rule WHERE active")
        return {row[0] for row in self.env.cr.fetchall()}

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env.registry.clear_cache()
        return records

    def write(self, vals):
        result = super().write(vals)
        self.env.registry.clear_cache()
        return result

    def unlink(self):
        result = super().unlink()
        self.env.registry.clear_cache()
        return result
