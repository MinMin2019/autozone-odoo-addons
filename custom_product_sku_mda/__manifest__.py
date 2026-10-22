{
    "name": "Autozone Product SKU - Item Approver",
    "version": "18.0.1.1.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "ผู้อนุมัติ Item Code (custom_master_data_approval) ได้สิทธิ์ผู้ดูแลรหัสสินค้า SKU อัตโนมัติ "
               "+ เมื่อเปิดอนุมัติไอเท็ม ออก SKU ตอนอนุมัติ (ไม่ใช่ตอนสร้าง) — โมดูลเชื่อม ติดตั้งเองเมื่อมีทั้งสองโมดูล",
    "depends": ["custom_product_sku", "custom_master_data_approval"],
    "data": ["security/security.xml"],
    "auto_install": True,
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
