from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    backdate = fields.Datetime(
        string="Actual Date (Backdate)",
        copy=False,
        tracking=True,
        help="กรอกก่อนกด Validate ถ้าวันที่รับ/โอนจริงไม่ใช่วันนี้ — "
        "ระบบจะใช้วันนี้ประทับลงใบโอน, stock move, มูลค่าสต๊อก "
        "และ JE ที่เกิดอัตโนมัติ แทนวันเวลาที่กด Validate",
    )

    @api.constrains("backdate")
    def _check_backdate(self):
        for picking in self:
            if picking.backdate and picking.backdate > fields.Datetime.now():
                raise ValidationError(
                    _("Actual Date (Backdate) must not be in the future.")
                )

    # ------------------------------------------------------------------
    # ตอน Validate: ประทับวันย้อนหลังตั้งแต่แรก
    # ------------------------------------------------------------------

    def _action_done(self):
        # แยกใบที่ backdate ออกมา validate ทีละใบพร้อม force_period_date
        # เพื่อให้ stock_account สร้าง JE ด้วยวันนั้นตั้งแต่แรก
        # (JE ที่ post แล้วแก้วันย้อนหลังไม่ได้ ต้องใช้ปุ่มแก้วันที่รับจริงแทน)
        res = True
        backdated = self.filtered("backdate")
        for picking in backdated:
            res = super(
                StockPicking,
                picking.with_context(force_period_date=picking.backdate.date()),
            )._action_done()
        remaining = self - backdated
        if remaining:
            res = super(StockPicking, remaining)._action_done()
        backdated._apply_backdate()
        return res

    def _apply_backdate(self):
        for picking in self.filtered(lambda p: p.backdate and p.state == "done"):
            picking._stamp_backdate(picking.backdate)

    def _stamp_backdate(self, date):
        """เขียนวันลงใบโอน, stock move, move line และชั้นมูลค่าสต๊อก"""
        self.ensure_one()
        self.date_done = date
        done_moves = self.move_ids.filtered(lambda m: m.state == "done")
        done_moves.write({"date": date})
        self.move_line_ids.write({"date": date})
        # รายงานมูลค่าสต๊อกย้อนหลัง (Inventory at Date) อ่านจาก
        # create_date ของ valuation layer ซึ่งเป็น magic field
        # เขียนผ่าน ORM ไม่ได้ ต้องอัพเดตตรงที่ DB
        svls = done_moves.sudo().stock_valuation_layer_ids
        if svls:
            self.env.cr.execute(
                "UPDATE stock_valuation_layer SET create_date = %s WHERE id IN %s",
                (date, tuple(svls.ids)),
            )
            svls.invalidate_recordset(["create_date"])

    # ------------------------------------------------------------------
    # แก้วันย้อนหลังหลังใบ done ไปแล้ว
    # ------------------------------------------------------------------

    def _backdate_journal_entries(self):
        """ใบสำคัญบัญชีที่เกิดจากใบโอนนี้ (เฉพาะที่ลงบัญชีแล้ว)"""
        moves = self.move_ids.sudo()
        entries = moves.account_move_ids | moves.stock_valuation_layer_ids.account_move_id
        return entries.filtered(lambda m: m.state == "posted")

    def action_fix_backdate(self):
        self.ensure_one()
        if self.state != "done":
            raise UserError(
                _("ใช้ได้เฉพาะใบที่ทำรายการเสร็จแล้ว ใบที่ยังไม่เสร็จให้กรอกช่อง "
                  "Actual Date (Backdate) ก่อนกด Validate")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("แก้วันที่รับจริง"),
            "res_model": "stock.backdate.fix",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_picking_id": self.id,
                "default_new_date": self.backdate or self.date_done,
            },
        }

    def _rewrite_backdate(self, new_date):
        """ย้ายวันของใบโอนที่ทำเสร็จไปแล้ว รวมถึงใบสำคัญบัญชีที่ผูกอยู่"""
        self.ensure_one()
        if self.state != "done":
            raise UserError(_("ใบโอนนี้ยังไม่เสร็จ แก้วันที่รับจริงไม่ได้"))
        if new_date > fields.Datetime.now():
            raise UserError(_("วันที่รับจริงต้องไม่เป็นวันในอนาคต"))

        old_date = self.date_done
        entries = self._backdate_journal_entries()
        results = entries._backdate_stock_entry_to(new_date.date())

        self._stamp_backdate(new_date)
        self.backdate = new_date

        # ให้ Odoo จับคู่บัญชีสินค้าขาเข้ากับบิลผู้ขายใหม่อีกรอบ (safety net)
        try:
            related = self.move_ids.sudo()._get_related_invoices()
            if related:
                related._stock_account_anglo_saxon_reconcile_valuation()
        except Exception:  # noqa: BLE001 - จับคู่ไม่สำเร็จไม่ควรทำให้การแก้วันล้ม
            pass

        self._backdate_log(old_date, new_date, results)
        return results

    def _backdate_log(self, old_date, new_date, results):
        """บันทึกลง Chatter ว่าใครแก้ จากวันไหนเป็นวันไหน ใบสำคัญเปลี่ยนเลขอะไรบ้าง"""
        self.ensure_one()
        lines = [
            Markup("<p><b>%s</b><br/>%s</p>")
            % (
                _("แก้วันที่รับจริงย้อนหลัง"),
                _("จาก %(old)s เป็น %(new)s", old=old_date, new=new_date),
            )
        ]
        if results:
            items = Markup("").join(
                Markup("<li>%s</li>")
                % _(
                    "%(old_name)s (%(old_date)s) → %(new_name)s (%(new_date)s)%(renum)s"
                    "%(recon)s",
                    old_name=r["old_name"],
                    old_date=r["old_date"],
                    new_name=r["new_name"],
                    new_date=r["new_date"],
                    renum=_(" — ออกเลขใหม่ เลขเดิมกลายเป็นช่องว่าง")
                    if r["renumbered"]
                    else _(" — เลขที่เดิม"),
                    recon=_(" — จับคู่กลับไม่ได้ %s กลุ่ม ต้องจับคู่เอง", r["recon_failed"])
                    if r["recon_failed"]
                    else "",
                )
                for r in results
            )
            lines.append(Markup("<ul>%s</ul>") % items)
        else:
            lines.append(Markup("<p>%s</p>") % _("ใบโอนนี้ไม่มีใบสำคัญบัญชีผูกอยู่"))
        self.message_post(body=Markup("").join(lines))
