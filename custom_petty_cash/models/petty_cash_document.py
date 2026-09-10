import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# กลุ่มที่แก้เลขที่เอกสารได้ — ตั้งใจให้เป็นกลุ่มแยก ไม่ผูกกับ account.group_*
# เพราะสิทธิ์บัญชีมาตรฐาน (Invoicing/Administrator) ธุรการสาขาก็มีเกือบทุกคน
# ถ้าใช้กลุ่มพวกนั้นเท่ากับเปิดให้ทุกคนแก้ = ไม่ได้คุมอะไรเลย
NAME_EDIT_GROUP = "custom_petty_cash.group_petty_cash_number_admin"


class PettyCashDocument(models.AbstractModel):
    """ฐานร่วมของเอกสารเงินสดย่อยทั้ง 4 แบบ — คุมเรื่องเลขที่เอกสารอย่างเดียว
    (โมเดลที่สืบทอดต้องมีฟิลด์ state ที่มีสถานะ 'draft')"""

    _name = "petty.cash.document"
    _description = "ฐานร่วมเอกสารเงินสดย่อย (เลขที่เอกสาร)"

    name = fields.Char(
        string="เลขที่เอกสาร", default="New", copy=False, tracking=True,
        help="ออกอัตโนมัติจากตัวนับของระบบ — ผู้ที่มีสิทธิ์ 'แก้เลขที่เอกสารเงินสดย่อย' "
        "แก้ได้เฉพาะตอนเอกสารยังเป็นร่าง และเลขห้ามซ้ำกับเอกสารเดิม")
    name_editable = fields.Boolean(
        compute="_compute_name_editable",
        help="ใช้เปิด/ปิดการแก้ช่องเลขที่เอกสารบนฟอร์ม")

    @api.depends_context("uid")
    def _compute_name_editable(self):
        allowed = self.env.user.has_group(NAME_EDIT_GROUP)
        for rec in self:
            rec.name_editable = allowed and rec.state == "draft"

    def init(self):
        """กันเลขซ้ำระดับฐานข้อมูล — partial index เพราะเรคคอร์ดที่ยังไม่ได้เลข
        (ตัวนับหาย/ยังไม่ตั้ง) ค้างเป็น 'New' ได้หลายใบพร้อมกัน"""
        if self._abstract:
            return  # ตัว mixin เองไม่มีตารางจริง
        index = f"{self._table}_name_uniq"
        self.env.cr.execute("SAVEPOINT petty_name_uniq")
        try:
            self.env.cr.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS "{index}" ON "{self._table}" '
                "(name) WHERE name IS NOT NULL AND name != 'New'")
        except Exception:  # noqa: BLE001 — ข้อมูลเดิมซ้ำอยู่ก่อน ห้ามทำให้ upgrade ล้ม
            self.env.cr.execute("ROLLBACK TO SAVEPOINT petty_name_uniq")
            _logger.warning(
                "custom_petty_cash: สร้าง unique index %s ไม่สำเร็จ — "
                "ตาราง %s มีเลขที่เอกสารซ้ำอยู่ ต้องแก้ข้อมูลซ้ำก่อนถึงจะกันเลขซ้ำได้",
                index, self._table)
        else:
            self.env.cr.execute("RELEASE SAVEPOINT petty_name_uniq")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    self._name) or "New"
            elif not self.env.su and not self.env.user.has_group(NAME_EDIT_GROUP):
                # คนที่ไม่มีสิทธิ์ยัดเลขเองผ่าน RPC/import ไม่ได้ — ให้ตัวนับออกให้
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    self._name) or "New"
        return super().create(vals_list)

    def write(self, vals):
        if "name" in vals:
            self._check_name_edit()
        return super().write(vals)

    def _check_name_edit(self):
        if self.env.su:
            return
        if not self.env.user.has_group(NAME_EDIT_GROUP):
            raise UserError(
                "แก้เลขที่เอกสารได้เฉพาะผู้ที่ได้รับสิทธิ์ "
                "'แก้เลขที่เอกสารเงินสดย่อย' (ฝ่ายบัญชี) — "
                "เลขนี้ออกจากตัวนับของระบบ ถ้าต้องแก้ให้แจ้งบัญชี")
        locked = self.filtered(lambda r: r.state != "draft")
        if locked:
            raise UserError(
                "แก้เลขที่เอกสารได้เฉพาะตอนเอกสารยังเป็น 'ร่าง' — "
                "เอกสารต่อไปนี้ยืนยันไปแล้ว: " + ", ".join(locked.mapped("name"))
                + "\nถ้าจำเป็นจริง ให้กดกลับเป็นร่างก่อน")
