{
    "name": "Consumption Summary by Branch (สรุปเบิกใช้วัสดุตามสาขา)",
    "version": "18.0.1.0.0",
    "category": "Autozone/Inventory",
    "author": "Autozone",
    "summary": "สรุปรายจ่ายเบิกใช้วัสดุ ตามสาขา × บัญชีค่าใช้จ่าย / หมวดสินค้า / เดือน ในช่วงวันที่ รวมวิธีเดิม (ส่งขายราคา 0) ให้เทียบ",
    "description": """
รายงานสรุปการเบิกใช้วัสดุ (Consumption Summary) ตามมาตรฐาน ERP

* แหล่งข้อมูล: ใบเบิกใช้วัสดุ (Operation Type CONS → location "เบิกใช้วัสดุ") หักเบิกคืน
  + ตัวเลือกรวม "ส่งขายราคา 0" (วิธีเดิมก่อนมี CONS) เพื่อเห็นภาพรวมต่อเนื่อง
* มูลค่า = จำนวน x ต้นทุน (valuation layer ของ move ถ้ามี ไม่มีใช้ต้นทุนมาตรฐาน)
* บัญชีค่าใช้จ่าย = บัญชีที่หมวดสินค้า/สินค้ากำหนด (ตัวเดียวกับที่ JE เบิกใช้ลง), สาขา = analytic ของ operation type CONS
* หน้าจอ pivot: แถว = สาขา, คอลัมน์ = บัญชีค่าใช้จ่าย (สลับเป็นหมวด/เดือน/สินค้าได้) + list/graph
* PDF: ตารางสาขา × บัญชีค่าใช้จ่าย + ตารางหมวดสินค้า; Excel: สรุป + รายการ
    """,
    "depends": ["stock_account", "custom_branch_consumption", "sale_stock", "autozone_report_fonts"],
    "data": [
        "security/ir.model.access.csv",
        "report/stock_consumption_report.xml",
        "wizard/stock_consumption_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
