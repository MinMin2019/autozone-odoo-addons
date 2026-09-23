from odoo import fields, models

TONES = [("one", "1 สี"), ("two", "2 สี"), ("none", "ไม่ผูกโทนสี")]
WORK_TYPES = [("part_paint", "พ่นชิ้นส่วน"), ("garage", "งานอู่"), ("service", "งานบริการ")]
WORK_STAGES = [
    ("dent", "งานเคาะ"),
    ("putty", "งานโป้ว"),
    ("prep", "งานเตรียมพ่น"),
    ("paint", "งานพ่นสี"),
    ("polish", "งานขัดสี"),
    ("assembly", "งานประกอบ"),
    ("wash", "งานล้างรถ"),
    ("qc", "งาน QC"),
    ("none", "ไม่ผูกขั้นตอน"),
]


class ProductTemplate(models.Model):
    _inherit = "product.template"

    az_brand_id = fields.Many2one(
        "az.product.brand", "แบรนด์", index=True, tracking=True, ondelete="restrict")
    az_subtype_id = fields.Many2one(
        "az.product.subtype", "ประเภทย่อย", index=True, tracking=True, ondelete="restrict")
    az_owner_id = fields.Many2one(
        "az.product.owner", "เจ้าของสินค้า", index=True, tracking=True, ondelete="restrict",
        help="ลูกค้าเจ้าของแบบ/เจ้าของงาน — เว้นว่างถ้าเป็นของที่หลายลูกค้าใช้ร่วมกัน")
    az_part_id = fields.Many2one(
        "az.car.part", "ชิ้นส่วน", index=True, tracking=True, ondelete="restrict")
    az_car_make_id = fields.Many2one(
        "az.car.make", "ยี่ห้อรถ", index=True, tracking=True, ondelete="restrict")
    az_car_model_id = fields.Many2one(
        "az.car.model", "รุ่นรถ", index=True, tracking=True, ondelete="restrict",
        domain="['|', ('make_id', '=', False), ('make_id', '=', az_car_make_id)]")
    az_tone = fields.Selection(TONES, "จำนวนโทนสี", index=True, tracking=True)
    az_work_type = fields.Selection(WORK_TYPES, "ประเภทงาน", index=True, tracking=True)
    az_work_stage = fields.Selection(WORK_STAGES, "ขั้นตอนงาน", index=True, tracking=True)
    az_old_categ_id = fields.Many2one(
        "product.category", "หมวดเดิม", index=True, readonly=True, copy=False, ondelete="set null",
        help="หมวดก่อนจัดหมวดใหม่ (ก.ย. 2569) เก็บไว้ตรวจย้อนหลัง")
    # เก็บชื่อหมวดเดิมเป็นข้อความด้วย เพราะพอลบหมวดเก่าทิ้ง az_old_categ_id จะว่าง (ondelete=set null)
    az_old_categ_name = fields.Char(
        "ชื่อหมวดเดิม", readonly=True, copy=False,
        help="ชื่อเต็มของหมวดก่อนจัดหมวดใหม่ (ก.ย. 2569) เก็บเป็นข้อความเพื่อให้ตรวจย้อนได้แม้หมวดเดิมถูกลบแล้ว")
