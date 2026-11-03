PURCHASE_TAB = ("seller_ids", "variant_seller_ids", "description_purchase", "purchase_line_warn")


def migrate(cr, version):
    # 1.2.2: ข้อมูลในแท็บ Purchase จัดซื้อแก้เองได้ (ผู้ขาย/ราคา, คำอธิบาย, คำเตือน)
    # ยังล็อค Control Policy (purchase_method) และ Purchase Unit (uom_po_id)
    # เติมต่อท้ายค่าเดิม — ไม่ทับคำนำหน้าที่ผู้ใช้ตั้งเองไว้
    cr.execute("""
        SELECT t.id, t.free_field_prefixes
          FROM az_approval_type t
          JOIN ir_model m ON m.id = t.model_id
         WHERE m.model = 'product.template'
    """)
    for type_id, current in cr.fetchall():
        prefixes = [p.strip() for p in (current or "").split(",") if p.strip()]
        prefixes += [p for p in PURCHASE_TAB if p not in prefixes]
        cr.execute("UPDATE az_approval_type SET free_field_prefixes = %s WHERE id = %s",
                   (", ".join(prefixes), type_id))
