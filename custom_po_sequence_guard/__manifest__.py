{
    "name": "Autozone PO Sequence Guard",
    "version": "18.0.1.1.0",
    "category": "Autozone/Purchase",
    "author": "Autozone",
    "summary": "ตัวนับเลข PO รายเดือน (คีย์ย้อนหลังได้เลขเดือนนั้น) + แก้เลขได้เฉพาะ RFQ + บังคับรูปแบบ PO+ปีเดือน+3 หลัก + กันเลข PO ซ้ำ (ข้ามเลขที่ถูกใช้แล้ว + ห้ามบันทึกเลขซ้ำ) และบันทึกทุกครั้งที่ตัวนับเลข PO เปลี่ยน "
               "หรือตัวนับเลขใดๆ ถอยหลัง (trigger ระดับฐานข้อมูล) ดูได้ที่ Settings > Technical > Sequence Audit",
    "depends": ["purchase"],
    "data": [
        "security/ir.model.access.csv",
        "views/az_sequence_audit_views.xml",
        "views/purchase_order_views.xml",
        "data/po_sequence_setup.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
