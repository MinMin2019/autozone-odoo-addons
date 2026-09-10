{
    "name": "Stock vs GL Reconciliation (กระทบยอดสต็อกกับบัญชี)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "กระทบยอด มูลค่าของในคลัง / ระบบสต็อก (valuation layer) / ยอดบัญชี 141xxx ณ วันที่ พร้อมแยกสาเหตุผลต่าง + บัญชีพักสินค้าขาเข้า-ขาออก",
    "description": """
รายงานกระทบยอดสต็อกกับบัญชี (Inventory to GL Reconciliation) ตามมาตรฐาน ERP ที่ Odoo ไม่มีในตัว

ส่วน A บัญชีสินค้าคงเหลือ (ต่อบัญชี 141xxx ที่ผูกกับหมวดสินค้า)
  * มูลค่าของในคลัง = จำนวนคงเหลือ ณ วันที่ x ต้นทุนปัจจุบัน
  * มูลค่าตามระบบสต็อก = ผลรวม stock.valuation.layer ณ วันที่
  * ยอดในบัญชี = ยอดคงเหลือ GL (posted) ณ วันที่
  * แยกสาเหตุผลต่าง บัญชี − ระบบสต็อก:
      - รายการสต็อกที่ไม่ได้ลงบัญชี (หมวด Manual / สินค้าไม่เก็บสต็อก)
      - รายการบัญชีที่ไม่ได้มาจากสต็อก (ลงตรงจากบิล / JV)
      - ผูกกันแต่ยอด/วันที่ไม่ตรง (cut-off)
  * ผลต่าง ระบบสต็อก − ของในคลัง (สินค้าผี / ต้นทุนต่าง) เจาะได้รายสินค้า
ส่วน B บัญชีพัก สินค้าขาเข้า / ขาออก
  * ยอดคงค้าง ณ วันที่ แยกตามสมุดรายวัน และแยกว่ามาจากใบรับ-ใบส่ง (ระบบสต็อก) หรือลงมือ
  * ยอดที่ยังไม่จับคู่ (unreconciled)
    """,
    "depends": ["stock_account", "autozone_report_fonts"],
    "data": [
        "security/ir.model.access.csv",
        "report/stock_gl_recon_report.xml",
        "wizard/stock_gl_recon_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
