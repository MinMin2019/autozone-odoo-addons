{
    "name": "Autozone PO Sequence Guard",
    "version": "18.0.1.0.0",
    "category": "Autozone/Purchase",
    "author": "Autozone",
    "summary": "กันเลข PO ซ้ำ (ข้ามเลขที่ถูกใช้แล้ว + ห้ามบันทึกเลขซ้ำ) และบันทึกทุกครั้งที่ตัวนับเลข PO เปลี่ยน "
               "หรือตัวนับเลขใดๆ ถอยหลัง (trigger ระดับฐานข้อมูล) ดูได้ที่ Settings > Technical > Sequence Audit",
    "depends": ["purchase"],
    "data": [
        "security/ir.model.access.csv",
        "views/az_sequence_audit_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
