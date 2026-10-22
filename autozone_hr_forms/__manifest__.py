{
    "name": "Autozone HR Forms",
    "summary": "แบบฟอร์มบุคคลในระบบ: ใบลาออก FM-HR-27, ประเมิน OJT FM-HR-12, Skill Map FM-HR-14, ความยินยอมข้อมูลอ่อนไหว",
    "description": """
Autozone HR Forms
=================

แบบฟอร์มกระดาษของฝ่ายบุคคล ทำเป็นระเบียนใน Odoo ตามช่องในฟอร์มจริง:

* FM-HR-27 ใบลาออก — อนุมัติตามลำดับ ผู้จัดการ → GM → แผนกบุคคล → กรรมการผู้จัดการ
  (หาจากผังองค์กร) พร้อมแบบสำรวจคืนของส่วน HR / ส่วนบัญชี แล้วลงลาออกในระบบได้จากใบลาออก
* FM-HR-12 ใบประเมินผลการปฏิบัติงานหลังการฝึกอบรม OJT — 10 หัวข้อ ผ่านที่ 40 คะแนน
* FM-HR-14 แบบประเมินทักษะ Skill Map — หัวข้อ Skill/Task ต่อตำแหน่ง ประเมินเป็นครั้ง
  ระดับ A–E, ผ่านทดลองงานที่ 75% และตาราง Skill Map Chart
* FM-HR-04 หน้า 3 การขอความยินยอมใช้ข้อมูลส่วนตัว (ข้อมูลอ่อนไหว 5 ข้อ) บนหน้าพนักงาน
""",
    "version": "18.0.1.2.0",
    "license": "LGPL-3",
    "author": "Autozone IT",
    "category": "Autozone/HR",
    "depends": [
        "hr_contract",
        "autozone_hr_recruitment",   # org-chart approver resolution (autozone.manpower.approver)
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/resignation_views.xml",
        "views/ojt_views.xml",
        "views/skillmap_views.xml",
        "views/hr_employee_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
