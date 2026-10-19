{
    "name": "Autozone Product SKU",
    "version": "18.0.1.3.1",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "รหัสสินค้า SKU 11 หลัก (หมวด 4 + แบรนด์ 3 + ลำดับ 4) ออกอัตโนมัติ, สินค้าดัมมี่ลำดับ 9001+, "
               "ล็อกหลังออกรหัส + ปุ่มออกรหัสใหม่/ยกเลิก SKU พร้อมประวัติ ไม่นำเลขเก่ากลับมาใช้, "
               "ติ๊กไม่ออก SKU รายตัว, หน้ารหัสหมวด SKU",
    "depends": ["custom_product_classification", "mail"],
    "data": [
        "security/security.xml",
        "data/mail_activity_type.xml",
        "security/ir.model.access.csv",
        "wizard/sku_reissue_views.xml",
        "wizard/sku_categ_code_views.xml",
        "views/product_views.xml",
        "views/category_views.xml",
        "views/sku_history_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
