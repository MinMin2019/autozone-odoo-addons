from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AzClassificationMaster(models.AbstractModel):
    """Common shape of every classification value list.

    Values are archived, never deleted, once used: their code may already be
    part of a product reference (SKU).
    """
    _name = "az.classification.master"
    _description = "Autozone classification value"
    _order = "sequence, name"

    # name of the product.template field that points at the concrete model
    _product_field = None

    name = fields.Char("ชื่อ", required=True)
    code = fields.Char("รหัส", help="ใช้ประกอบรหัสสินค้า (SKU) ภายหลัง — เลิกใช้แล้วห้ามนำรหัสกลับมาใช้ซ้ำ")
    sequence = fields.Integer("ลำดับ", default=10)
    active = fields.Boolean("ใช้งาน", default=True)
    note = fields.Char("หมายเหตุ")
    product_count = fields.Integer("จำนวนสินค้า", compute="_compute_product_count")

    def _compute_product_count(self):
        groups = self.env["product.template"].with_context(active_test=False)._read_group(
            [(self._product_field, "in", self.ids)], [self._product_field], ["__count"])
        counts = {rec.id: count for rec, count in groups}
        for rec in self:
            rec.product_count = counts.get(rec.id, 0)

    def _unique_extra_domain(self):
        return []

    @api.constrains("name", "code")
    def _check_unique_name_code(self):
        # case-insensitive, archived values included, so a retired code is never reused
        for rec in self:
            for fname in ("name", "code"):
                value = (rec[fname] or "").strip()
                if not value:
                    continue
                domain = [(fname, "=ilike", value), ("id", "!=", rec.id)] + rec._unique_extra_domain()
                if self.with_context(active_test=False).search_count(domain):
                    raise ValidationError(
                        f"{self._description}: {self._fields[fname].string} '{value}' "
                        "มีอยู่แล้ว (รวมรายการที่ปิดใช้งาน)")

    def action_view_products(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": "product.template",
            "view_mode": "list,kanban,form",
            "domain": [(self._product_field, "=", self.id)],
        }


class AzProductBrand(models.Model):
    _name = "az.product.brand"
    _inherit = "az.classification.master"
    _description = "แบรนด์ / ผู้ผลิต"
    _product_field = "az_brand_id"


class AzProductSubtype(models.Model):
    _name = "az.product.subtype"
    _inherit = "az.classification.master"
    _description = "ประเภทย่อย"
    _product_field = "az_subtype_id"


class AzProductOwner(models.Model):
    _name = "az.product.owner"
    _inherit = "az.classification.master"
    _description = "เจ้าของสินค้า"
    _product_field = "az_owner_id"

    partner_ids = fields.Many2many(
        "res.partner", string="บริษัทในกลุ่ม",
        help="ลูกค้าที่เป็นเจ้าของแบบ/เจ้าของงาน — กลุ่มเดียวใส่ได้หลายบริษัท เช่น RMA")


class AzCarPart(models.Model):
    _name = "az.car.part"
    _inherit = "az.classification.master"
    _description = "ชิ้นส่วน"
    _product_field = "az_part_id"


class AzCarMake(models.Model):
    _name = "az.car.make"
    _inherit = "az.classification.master"
    _description = "ยี่ห้อรถ"
    _product_field = "az_car_make_id"

    model_ids = fields.One2many("az.car.model", "make_id", string="รุ่น")


class AzCarModel(models.Model):
    _name = "az.car.model"
    _inherit = "az.classification.master"
    _description = "รุ่นรถ"
    _order = "make_id, sequence, name"
    _product_field = "az_car_model_id"

    make_id = fields.Many2one(
        "az.car.make", string="ยี่ห้อรถ", ondelete="restrict", index=True,
        help="ว่างไว้สำหรับค่าพิเศษ 'ไม่ผูกรุ่น' และ 'รอระบุ'")
    is_placeholder = fields.Boolean("ค่าพิเศษ", help="ไม่ใช่รุ่นจริง — ใช้บอกว่าไม่ผูกรุ่น หรือยังรอระบุ")

    def _unique_extra_domain(self):
        return [("make_id", "=", self.make_id.id)]

    @api.depends("name", "make_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.make_id.name} {rec.name}" if rec.make_id else rec.name
