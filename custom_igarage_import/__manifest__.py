{
    "name": "Autozone iGarage / AutoPart Import",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "ปุ่มดึงใบส่งของ (DO) จาก iGarage มาสร้างดราฟใบโอนสาขา และดึงยอดเบิกรายเดือนจาก iGarage / AutoPart "
               "มาสร้างดราฟใบเบิก ให้คลังตรวจก่อนยืนยัน",
    "description": """
ดึงข้อมูลจากระบบสาขา (iGarage, MySQL) และโปรแกรมโรงพ่นสี (AutoPart, SQL Server) มาสร้างเอกสารใน Odoo เป็น "ดราฟ" เท่านั้น
- ใบโอน: 1 ใบต่อ 1 DO (คลังกลาง AZG <-> สาขา) ใช้จำนวนส่ง (amount_sent) ข้าม DO ที่ยกเลิก/รออนุมัติ และ DO ที่ดึงแล้ว
- ใบเบิก: 1 ใบต่อสาขาต่อเดือน (iGarage: เบิกใช้ + ย้ายเข้าห้องสี ; ATP: AutoPart เบิก − คืน)
- จับคู่สินค้าด้วย SKU (az_sku) แล้วจึงรหัสสินค้า ; ตัวที่จับคู่ไม่ได้แสดงในผลการดึง ไม่สร้างแบบเดา
- ตั้งค่าการเชื่อมต่อที่ Inventory > Configuration > Settings (เฉพาะผู้ดูแลระบบ)
""",
    "depends": ["custom_branch_transfer", "custom_branch_consumption_ui", "base_setup", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/warehouse_map_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/import_wizard_views.xml",
        "views/branch_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
