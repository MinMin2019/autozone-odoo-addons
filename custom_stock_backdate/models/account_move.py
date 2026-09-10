from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _backdate_snapshot_reconciliation(self):
        """เก็บว่าบรรทัดของใบนี้เคยจับคู่กับบรรทัดไหนไว้บ้าง (ก่อนถูกปลดคู่)

        คืนค่าเป็น list ของ (account_id, [id ของบรรทัดคู่]) เพื่อเอาไปจับคู่กลับ
        หลังลงบัญชีใหม่ — บรรทัดของใบนี้จะได้ id ใหม่ไม่ได้ (ORM ไม่ลบทิ้ง)
        แต่ full/partial reconcile ถูกล้างไปแล้วใน button_draft
        """
        self.ensure_one()
        groups = []
        for line in self.line_ids.filtered("reconciled"):
            partials = line.matched_debit_ids | line.matched_credit_ids
            counterparts = (partials.debit_move_id | partials.credit_move_id) - line
            if counterparts:
                groups.append((line.account_id.id, counterparts.ids))
        return groups

    def _backdate_restore_reconciliation(self, groups):
        """จับคู่บรรทัดกลับตาม snapshot คืนจำนวนกลุ่มที่จับกลับไม่ได้"""
        self.ensure_one()
        AML = self.env["account.move.line"]
        failed = 0
        for account_id, counterpart_ids in groups:
            counterparts = AML.browse(counterpart_ids).exists().filtered(
                lambda l: not l.reconciled and l.move_id.state == "posted"
            )
            new_lines = self.line_ids.filtered(
                lambda l: l.account_id.id == account_id and not l.reconciled
            )
            if not counterparts or not new_lines:
                continue
            try:
                AML._reconcile_plan([new_lines | counterparts])
            except Exception:  # noqa: BLE001 - จับคู่ไม่ได้ไม่ควรทำให้ทั้งชุดล้ม
                failed += 1
        return failed

    def _backdate_check_target_lock_date(self, target_date):
        """เช็คว่าวันปลายทางไม่ตกในงวดที่ปิดแล้ว — ทำก่อนดึงใบกลับเป็นร่าง"""
        self.ensure_one()
        violations = self.company_id._get_lock_date_violations(
            target_date, fiscalyear=True, sale=False, purchase=False,
            tax=False, hard=True,
        )
        if violations:
            raise UserError(_(
                "วันที่ %(date)s อยู่ในงวดที่ปิดบัญชีไปแล้ว (%(info)s) ย้อนเข้าไปไม่ได้",
                date=target_date,
                info=self.env["res.company"]._format_lock_dates(violations),
            ))

    def _backdate_stock_entry_to(self, target_date):
        """ย้ายวันที่ของใบสำคัญที่ลงบัญชีแล้วไปเป็น target_date (datetime.date)

        ขั้นตอน: จำการจับคู่ -> ดึงกลับเป็นร่าง -> เปลี่ยนวัน
        -> ล้างเลขที่เฉพาะเมื่อข้ามเดือน -> ลงบัญชีใหม่ -> จับคู่กลับ
        คืนค่า list ของ dict สรุปผลต่อใบ เพื่อเอาไปเขียน chatter
        """
        result = []
        for move in self:
            if move.state != "posted":
                continue
            if move.inalterable_hash:
                raise UserError(
                    _(
                        "ใบสำคัญ %s ถูกล็อกด้วยลายเซ็นดิจิทัลแล้ว แก้วันที่ไม่ได้",
                        move.name,
                    )
                )
            # กันงวดที่ปิดแล้ว: เช็คทั้งวันเดิมและวันปลายทางก่อนแตะอะไรทั้งสิ้น
            move._check_fiscal_lock_dates()
            move._backdate_check_target_lock_date(target_date)
            old_name = move.name
            old_date = move.date

            groups = move._backdate_snapshot_reconciliation()
            move.button_draft()
            move.date = target_date
            renumbered = not move._sequence_matches_date()
            if renumbered:
                move.name = "/"
            move.action_post()
            failed = move._backdate_restore_reconciliation(groups)
            result.append(
                {
                    "old_name": old_name,
                    "new_name": move.name,
                    "old_date": old_date,
                    "new_date": move.date,
                    "renumbered": renumbered,
                    "recon_total": len(groups),
                    "recon_failed": failed,
                }
            )
        return result
