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
    approver_role_ids = fields.Many2many(
        "access.role", string="Role ผู้อนุมัติ (role builder)",
        help="ผูกกับ role ของ Access Role Builder: คนใน role เหล่านี้จะได้กลุ่มผู้อนุมัติ"
             "อัตโนมัติ (ผ่าน implied group) ทุกครั้งที่กด Apply role")
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

    def _user_is_approver(self, user):
        self.ensure_one()
        if user._is_admin() or user.has_group("base.group_system"):
            return True
        return self.approver_group_id in user.groups_id

    # ------------------------------------------------------------------
    # role builder integration
    # ------------------------------------------------------------------
    def _sync_role_implied(self):
        """เติมกลุ่มผู้อนุมัติเป็น implied ของกลุ่มที่ role builder generate
        — action_apply ของ role builder เขียนทับ implied_ids ทั้งชุดทุกครั้ง
        จึงต้องเรียกซ้ำหลัง apply เสมอ (ดู inherit ใน access_role.py)"""
        for t in self.sudo():
            for role in t.approver_role_ids:
                if role.group_id and t.approver_group_id not in role.group_id.implied_ids:
                    role.group_id.write({"implied_ids": [(4, t.approver_group_id.id)]})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_role_implied()
        return records

    def write(self, vals):
        res = super().write(vals)
        if "approver_role_ids" in vals or "approver_group_id" in vals:
            self._sync_role_implied()
        return res

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
