from odoo import _, api, fields, models


class StockBackdateFix(models.TransientModel):
    _name = "stock.backdate.fix"
    _description = "แก้วันที่รับจริงของใบโอนที่ทำเสร็จแล้ว"

    picking_id = fields.Many2one("stock.picking", required=True, readonly=True)
    current_date = fields.Datetime(
        string="วันที่ระบบบันทึกไว้ตอนนี้", related="picking_id.date_done", readonly=True
    )
    new_date = fields.Datetime(string="วันที่รับจริง", required=True)
    entry_ids = fields.Many2many(
        "account.move",
        string="ใบสำคัญบัญชีที่จะถูกแก้",
        compute="_compute_entry_ids",
    )
    warning = fields.Html(compute="_compute_warning")

    @api.depends("picking_id")
    def _compute_entry_ids(self):
        for wiz in self:
            wiz.entry_ids = wiz.picking_id._backdate_journal_entries()

    @api.depends("new_date", "entry_ids")
    def _compute_warning(self):
        for wiz in self:
            msgs = []
            if not wiz.entry_ids:
                msgs.append(
                    _("ใบโอนนี้ไม่มีใบสำคัญบัญชีผูกอยู่ — แก้เฉพาะฝั่งสต๊อกอย่างเดียว")
                )
            elif wiz.new_date:
                target = wiz.picking_id._backdate_local_date(wiz.new_date)
                crossing = wiz.entry_ids.filtered(
                    lambda m: (m.date.year, m.date.month) != (target.year, target.month)
                )
                if crossing:
                    msgs.append(
                        _(
                            "ข้ามเดือน: ใบสำคัญ %s จะถูกออกเลขใหม่ตามเดือนใหม่ "
                            "เลขเดิมจะกลายเป็นช่องว่างในสมุดรายวัน",
                            ", ".join(crossing.mapped("name")),
                        )
                    )
                else:
                    msgs.append(_("อยู่ในเดือนเดิม เลขที่ใบสำคัญจะไม่เปลี่ยน"))
            reconciled = wiz.entry_ids.line_ids.filtered("reconciled")
            if reconciled:
                msgs.append(
                    _(
                        "มีบรรทัดที่จับคู่กับบิลผู้ขายไว้ %s บรรทัด "
                        "ระบบจะปลดคู่แล้วจับกลับให้อัตโนมัติ",
                        len(reconciled),
                    )
                )
            wiz.warning = "".join("<div>• %s</div>" % m for m in msgs)

    def action_apply(self):
        self.ensure_one()
        self.picking_id._rewrite_backdate(self.new_date)
        return {"type": "ir.actions.act_window_close"}
