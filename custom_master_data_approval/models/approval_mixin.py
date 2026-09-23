from odoo import api, fields, models
from odoo.exceptions import UserError

ACTIVITY_XMLID = "custom_master_data_approval.mda_activity_approval"

# ฟิลด์เทคนิคที่ระบบเขียนเองระหว่าง flow ปกติ — ไม่ถือเป็น "การแก้ข้อมูล" จึงไม่ล็อค
FREE_FIELD_PREFIXES = ("message_", "activity_", "rating_", "website_message_")
FREE_FIELDS = {"customer_rank", "supplier_rank"}


class AzApprovalMixin(models.AbstractModel):
    """workflow อนุมัติข้อมูลหลัก: ร่าง → รออนุมัติ → อนุมัติแล้ว

    กติกา (เคาะ 25 ส.ค. 2026):
    - หน้างานแก้ได้เฉพาะสถานะร่าง กดส่งแล้วล็อคทันที (บังคับที่ write() ไม่ใช่แค่ view)
    - ผู้อนุมัติของประเภทนั้นเท่านั้นที่แก้ได้ทุกสถานะ
    - record ที่ระบบสร้างเอง (sudo) / ผู้อนุมัติสร้างเอง = อนุมัติทันที
    """

    _name = "az.approval.mixin"
    _description = "Master Data Approval Mixin"

    approval_state = fields.Selection(
        [("draft", "ร่าง"), ("to_approve", "รออนุมัติ"), ("approved", "อนุมัติแล้ว")],
        string="สถานะอนุมัติ", default="draft", copy=False, index=True,
        tracking=True)
    mda_reject_reason = fields.Text(
        string="เหตุผลที่ตีกลับล่าสุด", copy=False, readonly=True)
    mda_is_approver = fields.Boolean(
        compute="_compute_mda_is_approver", string="ผู้ใช้นี้อนุมัติได้")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _mda_type(self):
        return self.env["az.approval.type"]._get_for_model(self._name)

    def _mda_exempt(self):
        """record ที่ไม่เข้า workflow (override รายโมเดล เช่น ผู้ติดต่อย่อยของ partner)"""
        self.ensure_one()
        return False

    @api.depends_context("uid")
    def _compute_mda_is_approver(self):
        t = self._mda_type()
        val = bool(t) and t._user_is_approver(self.env.user)
        for rec in self:
            rec.mda_is_approver = val

    # ------------------------------------------------------------------
    # create/write guards
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        t = self._mda_type()
        auto = (
            not t
            or self.env.su
            or self.env.context.get("mda_auto_approve")
            or t._user_is_approver(self.env.user)
        )
        for vals in vals_list:
            if auto or self._mda_vals_exempt(vals):
                vals["approval_state"] = "approved"
            else:
                # กันยัดสถานะมากับ import/API
                vals["approval_state"] = "draft"
        return super().create(vals_list)

    @api.model
    def _mda_vals_exempt(self, vals):
        """เช็คตั้งแต่ตอน create ว่า record นี้ไม่เข้า workflow (override รายโมเดล)"""
        return False

    def write(self, vals):
        if self.env.su or self.env.context.get("mda_skip_check"):
            return super().write(vals)
        t = self._mda_type()
        if not t:
            return super().write(vals)
        free_prefixes = FREE_FIELD_PREFIXES + t._free_prefixes()
        meaningful = [
            f for f in vals
            if f not in FREE_FIELDS and not f.startswith(free_prefixes)
        ]
        if not meaningful or t._user_is_approver(self.env.user):
            return super().write(vals)
        # ผู้ใช้ทั่วไป: ห้ามแตะสถานะอนุมัติตรง ๆ (เปลี่ยนผ่านปุ่มเท่านั้น)
        if "approval_state" in meaningful:
            raise UserError(
                "เปลี่ยนสถานะอนุมัติโดยตรงไม่ได้ — ใช้ปุ่มส่งอนุมัติ/อนุมัติ/ตีกลับเท่านั้น")
        locked = self.filtered(
            lambda r: r.approval_state != "draft" and not r._mda_exempt())
        if locked:
            raise UserError(
                "ข้อมูลต่อไปนี้ส่งอนุมัติ/อนุมัติแล้ว แก้ไขได้เฉพาะผู้อนุมัติ (%s):\n%s\n\n"
                "→ หากต้องแก้ไข แจ้งผู้อนุมัติแก้ให้ หรือให้ผู้อนุมัติกดตีกลับเป็นร่าง"
                % (t.approver_group_id.full_name,
                   "\n".join("- %s" % r.display_name for r in locked[:20])))
        return super().write(vals)

    # ------------------------------------------------------------------
    # workflow actions
    # ------------------------------------------------------------------
    def action_mda_submit(self):
        t = self._mda_type()
        if not t:
            raise UserError("ประเภทการอนุมัติของโมเดลนี้ถูกปิดใช้งานอยู่")
        todo = self.filtered(lambda r: r.approval_state == "draft")
        if not todo:
            # เคสปกติ: ผู้อนุมัติกดปุ่มบนฟอร์มใหม่ — record ถูกอนุมัติอัตโนมัติ
            # ตั้งแต่ตอนเซฟแล้ว ไม่ต้องส่ง / หรือกดซ้ำตอนรออนุมัติอยู่
            if all(r.approval_state == "approved" for r in self):
                msg = ("ข้อมูลนี้อนุมัติแล้ว — ข้อมูลที่ผู้อนุมัติสร้างเอง"
                       "จะอนุมัติอัตโนมัติ ไม่ต้องกดส่ง")
            else:
                msg = "ข้อมูลนี้ส่งอนุมัติไปแล้ว กำลังรอผู้อนุมัติ"
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {"type": "info", "message": msg,
                           "next": {"type": "ir.actions.act_window_close"}},
            }
        # ผู้สร้างบาง role เป็น append-only (ไม่มีสิทธิ์ write) จึงต้อง sudo
        # เฉพาะการเปลี่ยนสถานะ หลังตรวจเงื่อนไขครบแล้ว
        todo.sudo().write({"approval_state": "to_approve"})
        todo._mda_notify_approvers(t)

    def _mda_post(self, body):
        # โพสต์ด้วย sudo แต่คงชื่อคนทำเป็น author — เหตุผล 2 ข้อ:
        # 1) message_post บังคับให้ผู้โพสต์มีอีเมล (user หน้างานบางคนไม่มี)
        # 2) การโพสต์ต้องมีสิทธิ์เขียนเอกสาร แต่ผู้อนุมัติ role-based บางคน
        #    ไม่มี ACL เขียน partner/product — สิทธิ์ workflow เราตรวจเองแล้ว
        email_from = (self.env.user.email_formatted
                      or self.env.company.email_formatted
                      or "odoo@localhost")
        author = self.env.user.partner_id
        for rec in self:
            rec.sudo().message_post(
                body=body, author_id=author.id, email_from=email_from)

    def _mda_notify_approvers(self, t):
        approvers = t.approver_group_id.sudo().users.filtered("active")
        activity_type = self.env.ref(ACTIVITY_XMLID, raise_if_not_found=False)
        for rec in self:
            rec._mda_post("ส่งขออนุมัติข้อมูลหลักโดย %s" % self.env.user.name)
            for user in approvers:
                rec.sudo().activity_schedule(
                    ACTIVITY_XMLID if activity_type else "mail.mail_activity_data_todo",
                    user_id=user.id,
                    summary="อนุมัติข้อมูลหลัก: %s" % rec.display_name,
                    note="ส่งโดย %s — ตรวจสอบและกดอนุมัติ/ตีกลับ" % self.env.user.name,
                )

    def action_mda_approve(self):
        t = self._mda_type()
        if not t or not t._user_is_approver(self.env.user):
            raise UserError("เฉพาะผู้อนุมัติ (%s) เท่านั้นที่กดอนุมัติได้"
                            % (t and t.approver_group_id.full_name or "-"))
        bad = self.filtered(lambda r: r.approval_state == "approved")
        if bad:
            raise UserError("อนุมัติแล้ว: " + ", ".join(bad.mapped("display_name")))
        self.sudo().write({"approval_state": "approved", "mda_reject_reason": False})
        self._mda_clear_approval_activities()
        self._mda_post("อนุมัติข้อมูลหลักโดย %s" % self.env.user.name)

    def action_mda_open_reject_wizard(self):
        t = self._mda_type()
        if not t or not t._user_is_approver(self.env.user):
            raise UserError("เฉพาะผู้อนุมัติเท่านั้นที่ตีกลับได้")
        return {
            "type": "ir.actions.act_window",
            "name": "ตีกลับข้อมูลหลัก",
            "res_model": "az.mda.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_res_model": self._name,
                "default_res_ids": ",".join(str(i) for i in self.ids),
            },
        }

    def _mda_do_reject(self, reason):
        """เรียกจาก wizard เท่านั้น (wizard เช็คสิทธิ์ผู้อนุมัติแล้ว)"""
        self.sudo().write({"approval_state": "draft", "mda_reject_reason": reason})
        self._mda_clear_approval_activities()
        for rec in self:
            rec._mda_post(
                "ตีกลับโดย %s — เหตุผล: %s" % (self.env.user.name, reason))
            creator = rec.sudo().create_uid
            if creator and creator.active and creator != self.env.user:
                rec.sudo().activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=creator.id,
                    summary="ข้อมูลหลักถูกตีกลับ: %s" % rec.display_name,
                    note="เหตุผล: %s — แก้ไขแล้วส่งอนุมัติใหม่" % reason,
                )

    def _mda_clear_approval_activities(self):
        if self.env.ref(ACTIVITY_XMLID, raise_if_not_found=False):
            self.sudo().activity_unlink([ACTIVITY_XMLID])
