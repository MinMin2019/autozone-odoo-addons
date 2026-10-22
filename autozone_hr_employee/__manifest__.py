{
    "name": "Autozone HR Employee",
    "summary": "รหัสพนักงานเห็นชัด, ชื่อพนักงานภาษาอังกฤษ และสัญญาจ้างแบบมีกำหนด / ไม่มีกำหนดระยะเวลา",
    "description": """
Autozone HR Employee
====================

* รหัสพนักงานเห็นชัด: ข้างชื่อในหน้าพนักงาน, บนการ์ด, คอลัมน์แรกของรายการ
  (Odoo ซ่อนไว้ในแท็บ Payroll) — ห้ามซ้ำอยู่แล้วจาก hr_payroll
* ชื่อ-นามสกุลภาษาอังกฤษ ใต้ชื่อภาษาไทยในหน้าพนักงาน ค้นหาได้จากช่องค้นหา
  และเห็นได้ทุกคน (Directory / Org Chart) เหมือนชื่อไทย
* ประเภทสัญญาจ้าง 2 แบบตามกฎหมายแรงงาน: มีกำหนดระยะเวลา (ต้องมีวันสิ้นสุด)
  และไม่มีกำหนดระยะเวลา แทนช่อง Contract Type 10 แบบของ Odoo ที่ไม่ได้ใช้
* ที่อยู่พนักงาน: จังหวัดเป็นชื่อไทย (แทน Chonburi ฯลฯ) และอำเภอมี "อ." / "เขต" นำหน้า
  ทั้งข้อมูลเดิม (ตอน Upgrade) และทุกครั้งที่บันทึก
* บัญชีธนาคารรับเงินเดือนแยกเป็นช่องเฉพาะ HR (ธนาคาร เลขที่ ชื่อบัญชี สาขา) แทนช่อง
  Bank Account ของ Odoo ที่ใช้ร่วมกับระบบบัญชี และเมนู "บัญชีธนาคารพนักงาน" ไว้กรอกทีละหลายคน
* พิมพ์สัญญาจ้างจากหน้าสัญญา: สัญญาจ้างแรงงาน / สัญญาจ้างลูกจ้างชั่วคราว ตามประเภท
  พร้อมช่องที่สัญญากระดาษใช้แต่ Odoo ไม่มี (วันที่ทำสัญญา เขียนที่ พยาน ทดลองงาน
  เงื่อนไขประเมิน/ต่อสัญญา และวันออก/หมดอายุบัตรประชาชน)
""",
    "version": "18.0.1.3.0",
    "license": "LGPL-3",
    "author": "Autozone IT",
    "category": "Autozone/HR",
    "depends": [
        "hr_contract",
        "hr_payroll",   # registration_number (รหัสพนักงาน) is defined here, not in hr
        "autozone_report_fonts",   # Sarabun for the printed contract
    ],
    "data": [
        "views/hr_employee_views.xml",
        "report/employment_contract.xml",
        "views/hr_contract_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "auto_install": False,
    "application": False,
}
