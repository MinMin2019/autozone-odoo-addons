import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockBackdateBulk(models.TransientModel):
    _name = "stock.backdate.bulk"
    _description = "แก้วันที่รับจริงเป็นชุดตามวันที่ตามกำหนดการ"

    picking_ids = fields.Many2many("stock.picking", string="ใบโอนที่เลือก")
    date_source = fields.Selection(
        [("scheduled", "วันที่ตามกำหนดการของแต่ละใบ"), ("fixed", "กำหนดวันเดียวกันทุกใบ")],
        default="scheduled",
        required=True,
        string="ยึดวันจาก",
    )
    fixed_date = fields.Datetime(string="วันที่รับจริง")
    skip_forward = fields.Boolean(
        string="ข้ามใบที่วันกำหนดการอยู่หลังวันที่ระบบบันทึก",
        default=True,
        help="ใบพวกนี้ไม่ใช่การคีย์ย้อนหลัง แต่เป็นของที่มาถึงช้ากว่านัด "
        "ถ้าแก้จะเป็นการเลื่อนวันไปข้างหน้าซึ่งไม่ใช่สิ่งที่ต้องการ",
    )
    same_month_only = fields.Boolean(
        string="ทำเฉพาะใบที่ไม่ข้ามเดือน",
        help="เลือกไว้ = แก้เฉพาะใบที่วันใหม่อยู่เดือนเดียวกับวันเดิม "
        "เลขที่ใบสำคัญจะไม่เปลี่ยนเลย ไม่มีช่องว่างในสมุดรายวัน",
    )
    preview = fields.Html(compute="_compute_preview", string="สรุปก่อนทำ")

    # ------------------------------------------------------------------

    def _target_date(self, picking):
        """วันที่จะใช้กับใบนี้ (None = ไม่เข้าเงื่อนไข ข้ามไป)"""
        self.ensure_one()
        target = self.fixed_date if self.date_source == "fixed" else picking.scheduled_date
        if not target or not picking.date_done:
            return None
        if target > fields.Datetime.now():
            return None
        if self.skip_forward and target >= picking.date_done:
            return None
        if self.same_month_only and (
            (target.year, target.month) != (picking.date_done.year, picking.date_done.month)
        ):
            return None
        return target

    def _candidates(self):
        """คืน list ของ (picking, target_date) เรียงตามวันใหม่จากเก่าไปใหม่

        เรียงเพื่อให้เลขที่ใบสำคัญที่ออกใหม่ไล่ตามวันจริง ไม่สลับไปมา
        """
        self.ensure_one()
        pairs = []
        for picking in self.picking_ids:
            if picking.state != "done":
                continue
            target = self._target_date(picking)
            if target:
                pairs.append((picking, target))
        return sorted(pairs, key=lambda pair: pair[1])

    @api.depends("picking_ids", "date_source", "fixed_date", "skip_forward", "same_month_only")
    def _compute_preview(self):
        for wiz in self:
            pairs = wiz._candidates()
            skipped = len(wiz.picking_ids) - len(pairs)
            entries = self.env["account.move"]
            renumber = self.env["account.move"]
            months = {}
            for picking, target in pairs:
                picking_entries = picking._backdate_journal_entries()
                entries |= picking_entries
                renumber |= picking_entries.filtered(
                    lambda m: (m.date.year, m.date.month) != (target.year, target.month)
                )
                key = (picking.date_done.strftime("%Y-%m"), target.strftime("%Y-%m"))
                months[key] = months.get(key, 0) + 1
            rows = "".join(
                "<tr><td>%s</td><td>%s</td><td class='text-end'>%s</td></tr>" % (src, dst, n)
                for (src, dst), n in sorted(months.items())
            )
            wiz.preview = """
                <div><b>จะแก้ %(n)s ใบ</b> (ข้าม %(skip)s ใบที่ไม่เข้าเงื่อนไข)</div>
                <div>ใบสำคัญบัญชีที่กระทบ %(je)s ใบ — ในนั้นจะถูกออกเลขใหม่ %(re)s ใบ</div>
                <table class="table table-sm mt-2">
                  <thead><tr><th>จากเดือน</th><th>ไปเดือน</th><th class="text-end">จำนวนใบ</th></tr></thead>
                  <tbody>%(rows)s</tbody>
                </table>
            """ % {
                "n": len(pairs),
                "skip": skipped,
                "je": len(entries),
                "re": len(renumber),
                "rows": rows or "<tr><td colspan='3'>—</td></tr>",
            }

    # ------------------------------------------------------------------

    def action_apply(self):
        self.ensure_one()
        pairs = self._candidates()
        if not pairs:
            raise UserError(_("ไม่มีใบไหนเข้าเงื่อนไข ลองปรับตัวเลือกด้านบน"))
        done = self.env["stock.picking"]
        failed = []
        for picking, target in pairs:
            # savepoint ต่อใบ: ใบไหนพังก็ข้ามไป ไม่ล้มทั้งชุด
            try:
                with self.env.cr.savepoint():
                    picking._rewrite_backdate(target)
                done |= picking
            except Exception as err:  # noqa: BLE001
                _logger.warning("backdate bulk failed on %s: %s", picking.name, err)
                failed.append((picking.name, str(err)))
        return self._result_action(done, failed)

    def _result_action(self, done, failed):
        message = _("แก้สำเร็จ %(ok)s ใบ", ok=len(done))
        if failed:
            detail = "\n".join("%s: %s" % (name, err) for name, err in failed[:20])
            message += _("\nไม่สำเร็จ %(bad)s ใบ:\n%(detail)s", bad=len(failed), detail=detail)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("แก้วันที่รับจริงเป็นชุด"),
                "message": message,
                "type": "warning" if failed else "success",
                "sticky": True,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
