# 1.2.3: ฟิลด์ที่ปลดทีละตัวย้ายจากช่องคำนำหน้า (พิมพ์เอง) ไปเป็นตารางเลือกฟิลด์
# ชื่อฟิลด์แท็บ Purchase ที่ 1.2.2 ใส่ไว้ในช่องคำนำหน้า → ย้ายไป free_field_ids
# purchase_line_warn เดิมครอบ 2 ฟิลด์ (warn + warn_msg) จึงเลือกให้ทั้งคู่
MOVE = {
    "seller_ids": ["seller_ids"],
    "variant_seller_ids": ["variant_seller_ids"],
    "description_purchase": ["description_purchase"],
    "purchase_line_warn": ["purchase_line_warn", "purchase_line_warn_msg"],
}
# ติดตั้งจาก 1.2.1 ตรงมา (ไม่เคยผ่าน 1.2.2) migration 1.2.2 รันก่อนอยู่แล้ว
# จึงเจอชื่อชุดนี้ในช่องคำนำหน้าเสมอ


def migrate(cr, version):
    cr.execute("""
        SELECT t.id, t.free_field_prefixes, t.model_id
          FROM az_approval_type t
          JOIN ir_model m ON m.id = t.model_id
         WHERE m.model = 'product.template'
    """)
    for type_id, current, model_id in cr.fetchall():
        prefixes = [p.strip() for p in (current or "").split(",") if p.strip()]
        names = [n for p in prefixes if p in MOVE for n in MOVE[p]]
        keep = [p for p in prefixes if p not in MOVE]
        cr.execute("UPDATE az_approval_type SET free_field_prefixes = %s WHERE id = %s",
                   (", ".join(keep) or None, type_id))
        if names:
            cr.execute("""
                INSERT INTO az_approval_type_free_field_rel (type_id, field_id)
                SELECT %s, f.id FROM ir_model_fields f
                 WHERE f.model_id = %s AND f.name IN %s
                ON CONFLICT DO NOTHING
            """, (type_id, model_id, tuple(names)))
