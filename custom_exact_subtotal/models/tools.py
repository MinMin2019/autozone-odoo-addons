# -*- coding: utf-8 -*-
"""ตัวช่วยกลางของ "ยอดรวมกำหนดเอง" ใช้ร่วมกันทั้ง sale.order.line และ account.move.line"""

from odoo import _
from odoo.exceptions import ValidationError

# เพดานส่วนต่างระหว่างยอดกำหนดเองกับยอดที่คำนวณตามปกติ (กันพิมพ์ผิดหลักเท่านั้น)
# 1% กว้างกว่าเศษปัดทศนิยมที่โมดูลนี้ออกแบบมารองรับหลายพันเท่า
DEVIATION_LIMIT = 0.01


def exact_unit_price(subtotal, quantity, discount=0.0):
    """ราคาต่อหน่วยความละเอียดเต็ม (double) ที่ทำให้
    quantity x price x (1 - discount/100) = subtotal พอดี

    คืน None เมื่อไม่ได้กำหนดยอดเอง หรือคำนวณย้อนกลับไม่ได้ (จำนวน 0 / ส่วนลด 100%)
    ซึ่งแปลว่า "ปล่อยให้ Odoo ทำงานตามปกติ"
    """
    if not subtotal:
        return None
    factor = (quantity or 0.0) * (1.0 - (discount or 0.0) / 100.0)
    if not factor:
        return None
    return subtotal / factor


def natural_subtotal(line, quantity):
    """ยอดรวมที่ Odoo จะคำนวณได้ตามปกติ (จำนวน x ราคาต่อหน่วย x ส่วนลด)"""
    return (quantity or 0.0) * line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)


def check_exact_subtotal(line, quantity, taxes):
    """ตรวจยอดกำหนดเองตอนบันทึก -- บล็อกถ้าใช้ไม่ได้จริง (เรียกจาก @api.constrains)

    หมายเหตุ: constrains ต้องผูกกับ 'exact_subtotal' อย่างเดียว ห้ามใส่ฟิลด์ที่เป็น
    compute (price_unit / product_uom_qty / tax_id ล้วนเป็น compute+store บน
    sale.order.line) เพราะ _compute_field_value จะเรียก _validate_fields ต่อ
    ทำให้ตัว check วิ่งซ้อนอยู่กลางวงจรคำนวณราคา แล้วอ่านค่าที่ยังไม่นิ่ง
    การเตือนเมื่อแก้จำนวน/ราคาทีหลังใช้ onchange แทน (ดู _onchange_exact_subtotal_stale)
    """
    if not line.exact_subtotal:
        return

    # ภาษีแบบรวมใน (tax included) คำนวณยอดก่อนภาษีถอยหลังจากราคา สูตรถอดราคาต่อหน่วย
    # ของโมดูลนี้จึงใช้ไม่ได้ ต้องกันไว้ ไม่ปล่อยให้ยอดเพี้ยนเงียบ ๆ
    included = taxes.filtered("price_include")
    if included:
        raise ValidationError(_(
            'บรรทัด "%(line)s" กำหนดยอดรวมเองไม่ได้ เพราะภาษี %(tax)s เป็นแบบรวมในราคา\n\n'
            "ยอดรวมกำหนดเองรองรับเฉพาะภาษีแบบแยกนอก (ราคาไม่รวมภาษี)",
            line=line.name or "-",
            tax=", ".join(included.mapped("name")),
        ))

    natural = natural_subtotal(line, quantity)
    if not natural:
        raise ValidationError(_(
            'บรรทัด "%(line)s" กำหนดยอดรวมเองไม่ได้ เพราะจำนวนหรือราคาต่อหน่วยเป็น 0\n\n'
            "กรอกจำนวนและราคาต่อหน่วยตามปกติก่อน แล้วค่อยใส่ยอดรวมที่ต้องการ",
            line=line.name or "-",
        ))

    if abs(line.exact_subtotal - natural) > abs(natural) * DEVIATION_LIMIT:
        raise ValidationError(_(
            'ยอดรวมกำหนดเองของบรรทัด "%(line)s" ต่างจากยอดปกติเกิน %(limit)s%%\n\n'
            "ยอดที่กรอก: %(exact)s\n"
            "ยอดตามจำนวน x ราคาต่อหน่วย: %(natural)s\n\n"
            "ช่องนี้มีไว้ชดเชยเศษปัดทศนิยมเท่านั้น (ต่างกันไม่กี่สตางค์)\n"
            "ถ้าเพิ่งแก้จำนวนหรือราคาต่อหน่วย ให้แก้ยอดรวมกำหนดเองตามด้วย "
            "หรือล้างช่องนี้เพื่อกลับไปคำนวณแบบปกติ",
            line=line.name or "-",
            limit=DEVIATION_LIMIT * 100,
            exact="{:,.2f}".format(line.exact_subtotal),
            natural="{:,.2f}".format(natural),
        ))


def stale_warning(line, quantity):
    """คำเตือน (ไม่บล็อก) เมื่อแก้จำนวน/ราคาแล้วยอดกำหนดเองค้างของเก่า"""
    if not line.exact_subtotal:
        return None
    natural = natural_subtotal(line, quantity)
    if natural and abs(line.exact_subtotal - natural) <= abs(natural) * DEVIATION_LIMIT:
        return None
    return {
        "title": _("ยอดรวมกำหนดเองไม่ตรงกับจำนวน/ราคาแล้ว"),
        "message": _(
            'บรรทัด "%(line)s" ยังค้างยอดรวมกำหนดเอง %(exact)s '
            "แต่จำนวน x ราคาต่อหน่วยตอนนี้ได้ %(natural)s\n\n"
            "แก้ยอดรวมกำหนดเองให้ตรง หรือล้างช่องนั้นเพื่อกลับไปคำนวณแบบปกติ "
            "(ถ้าไม่แก้ ระบบจะไม่ยอมให้บันทึก)",
            line=line.name or "-",
            exact="{:,.2f}".format(line.exact_subtotal),
            natural="{:,.2f}".format(natural),
        ),
    }
