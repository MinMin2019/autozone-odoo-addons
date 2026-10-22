{
    "name": "Autozone HR Blacklist",
    "summary": "ติด Blacklist ตอนลงพนักงานลาออก แล้วกันไม่ให้รับกลับเข้ามาใหม่",
    "description": """
Autozone HR Blacklist
=====================

ตอนลงพนักงานลาออก (Archive → หน้าต่าง Departure) ติ๊ก "ติด Blacklist ห้ามรับกลับ" พร้อมเหตุผลได้

ถ้าคนนั้นกลับมาอีก ระบบจับจากเลขบัตรประชาชน ชื่อ-นามสกุล เบอร์โทร หรืออีเมล:

* ผู้สมัคร (Recruitment) ขึ้นป้ายแดง และเลื่อนขั้นตอนหรือกด Create Employee ไม่ได้
* สร้างพนักงานใหม่ หรือกู้ระเบียนเก่ากลับมา (Unarchive) ไม่ได้

HR Manager (Employees: Administrator) ทำต่อได้ทุกกรณี และปลด Blacklist ได้คนเดียว
""",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "author": "Autozone IT",
    "category": "Autozone/HR",
    "depends": [
        "hr_recruitment",
        "hr_payroll",       # registration_number (รหัสพนักงาน) lives here, not in hr
    ],
    "data": [
        "views/hr_employee_views.xml",
        "views/hr_candidate_views.xml",
        "wizard/hr_departure_wizard_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
