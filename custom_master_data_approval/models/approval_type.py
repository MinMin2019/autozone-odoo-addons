from odoo import api, fields, models
from odoo.exceptions import UserError


class AzApprovalType(models.Model):
    """ประเภทการอนุมัติข้อมูลหลัก — 1 record ต่อ 1 โมเดล (เช่น res.partner, product.template)

    ออกแบบเป็น config เพื่อให้เพิ่มการอนุมัติโมเดลอื่นในอนาคตได้โดยแทบไม่ต้องแก้โค้ด:
    ใส่ az.approval.mixin ให้โมเดลใหม่ + สร้าง record ประเภทที่นี่ + เพิ่มจุดบล็อกของโมเดลนั้น
    """

    _name = "az.approval.type"
    _description = "ประเภทการอนุมัติข้อมูลหลัก"

    name = fields.Char(string="ชื่อ", required=True, translate=False)
    model_id = fields.Many2one(
        "ir.model", string="โมเดล", required=True, ondelete="cascade",
        help="โมเดลที่ใช้ workflow อนุมัติ (ต้องสืบทอด az.approval.mixin ในโค้ดด้วย)")
    model_name = fields.Char(related="model_id.model", store=True, index=True)
    approver_group_id = fields.Many2one(
        "res.groups", string="กลุ่มผู้อนุมัติ", required=True,
        help="สมาชิกกลุ่มนี้กดอนุมัติ/ตีกลับได้ และเป็นกลุ่มเดียวที่แก้ไขข้อมูล"
             "หลังส่งอนุมัติได้")
    approver_user_ids = fields.Many2many(
        "res.users", string="ผู้อนุมัติ",
        compute="_compute_approver_user_ids", inverse="_inverse_approver_user_ids",
        domain=[("share", "=", False)],
        help="รายชื่อผู้อนุมัติของประเภทนี้ — เพิ่ม/ลบที่นี่ ระบบจะใส่/ถอด user "
             "ออกจากกลุ่มผู้อนุมัติให้เอง (admin ของระบบอนุมัติได้เสมอเป็นทางสำรอง). "
             "ให้ทั้ง role ได้สิทธิ์: ไปที่ role แล้วใส่กลุ่มผู้อนุมัติในช่อง Extra Permissions "
             "— คนใน role จะขึ้นชื่อที่นี่เอง (คนที่มาจาก role ให้ถอดที่ role)")
    approver_warning = fields.Char(compute="_compute_approver_user_ids")
    free_field_prefixes = fields.Char(
        string="ฟิลด์ที่แก้ได้โดยไม่ต้องอนุมัติ (คำนำหน้า)",
        help="คำนำหน้าชื่อฟิลด์ คั่นด้วยจุลภาค เช่น az_ — ฟิลด์ที่ชื่อขึ้นต้นแบบนี้แก้ได้ทุกสถานะ "
             "โดยไม่ล็อค (ยังมีประวัติการแก้ในแชท) ใช้กับข้อมูลจัดกลุ่มที่คลัง/จัดซื้อช่วยดูแล "
             "เช่น แบรนด์ ชิ้นส่วน ขั้นตอนงาน และค่าที่ระบบคำนวณเอง เช่น ชั้น ABC")
    active = fields.Boolean(
        default=True, string="เปิดใช้งาน",
        help="ปิด = พัก workflow ทั้งประเภท (ไม่ล็อคการแก้ไข ไม่บล็อกทรานแซคชัน) "
             "ใช้เป็นสวิตช์ฉุกเฉินได้โดยไม่ต้องถอนโมดูล")

    _sql_constraints = [
        ("model_uniq", "unique(model_id)", "โมเดลนี้มีประเภทการอนุมัติอยู่แล้ว"),
    ]

    # ------------------------------------------------------------------
    # lookup / permission helpers (ทุกทางเรียกจาก runtime ใช้ sudo ภายใน
    # เพื่อไม่ต้องแจก ACL อ่าน config ให้ผู้ใช้ทั่วไป)
    # ------------------------------------------------------------------
    @api.model
    def _get_for_model(self, model_name):
        """คืนประเภทการอนุมัติที่เปิดใช้ของโมเดลนั้น (empty recordset = workflow ปิด)"""
        return self.sudo().search([("model_name", "=", model_name)], limit=1)

    def _free_prefixes(self):
        self.ensure_one()
        return tuple(p.strip() for p in (self.free_field_prefixes or "").split(",") if p.strip())

    def _user_is_approver(self, user):
        self.ensure_one()
        if user._is_admin() or user.has_group("base.group_system"):
            return True
        return self.approver_group_id in user.groups_id

    # ------------------------------------------------------------------
    # ผู้อนุมัติ = สมาชิกกลุ่มผู้อนุมัติ (จุดเช็คสิทธิ์ทุกที่ยังดูที่กลุ่มเหมือนเดิม)
    # ------------------------------------------------------------------
    @api.depends("approver_group_id", "approver_group_id.users")
    def _compute_approver_user_ids(self):
        for t in self:
            users = t.approver_group_id.sudo().users.filtered("active")
            t.approver_user_ids = users
            if not users:
                t.approver_warning = ("ยังไม่มีผู้อนุมัติ — ตอนนี้มีแต่ admin ของระบบที่อนุมัติได้")
            elif len(users) < 2:
                t.approver_warning = ("มีผู้อนุมัติคนเดียว — ถ้าคนนี้ลา/ไม่อยู่ งานหน้าบ้านจะติด "
                                      "แนะนำให้มีอย่างน้อย 2 คน")
            else:
                t.approver_warning = False

    def _inverse_approver_user_ids(self):
        for t in self:
            if t.approver_group_id:
                t.approver_group_id.sudo().write(
                    {"users": [(6, 0, t.approver_user_ids.ids)]})

    # ------------------------------------------------------------------
    # transaction gates — จุดบล็อกทุกที่เรียก 2 เมธอดนี้
    # ------------------------------------------------------------------
    @api.model
    def check_partners(self, partners, doc_label):
        """raise ถ้ามี partner ที่ยังไม่ผ่านการอนุมัติ (เช็คที่ตัวแม่/commercial partner
        — ผู้ติดต่อ/ที่อยู่ย่อยยึดสถานะตัวแม่ ไม่ต้องอนุมัติแยก)"""
        if self.env.su or not partners:
            return
        t = self._get_for_model("res.partner")
        if not t:
            return
        tops = partners.sudo().mapped("commercial_partner_id")
        bad = tops.filtered(lambda p: p.approval_state != "approved")
        if bad:
            raise UserError(self._blocked_message(bad, doc_label, "รายชื่อ (ลูกค้า/ผู้ขาย)"))

    @api.model
    def check_products(self, products, doc_label):
        """raise ถ้ามีสินค้า (variant หรือ template) ที่ยังไม่ผ่านการอนุมัติ"""
        if self.env.su or not products:
            return
        t = self._get_for_model("product.template")
        if not t:
            return
        if products._name == "product.product":
            templates = products.sudo().mapped("product_tmpl_id")
        else:
            templates = products.sudo()
        bad = templates.filtered(lambda p: p.approval_state != "approved")
        if bad:
            raise UserError(self._blocked_message(bad, doc_label, "สินค้า"))

    @api.model
    def _blocked_message(self, records, doc_label, kind):
        state_label = dict(
            records._fields["approval_state"]._description_selection(self.env))
        lines = "\n".join(
            "- %s (สถานะ: %s)" % (r.display_name, state_label.get(r.approval_state))
            for r in records[:20])
        more = "\n..." if len(records) > 20 else ""
        return (
            "ดำเนินการ%s ไม่ได้ — %sต่อไปนี้ยังไม่ผ่านการอนุมัติข้อมูลหลัก:\n%s%s\n\n"
            "→ ส่งข้อมูลให้ผู้อนุมัติกดอนุมัติก่อน แล้วจึงทำรายการอีกครั้ง"
            % (doc_label, kind, lines, more))
