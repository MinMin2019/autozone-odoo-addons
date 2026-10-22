{
    "name": "Autozone HR Recruitment",
    "summary": "ใบขออัตรากำลัง อนุมัติตามผังองค์กร และ Pipeline ผู้สมัครตาม Flow การสรรหาของฝ่ายบุคคล",
    "description": """
Autozone HR Recruitment
=======================

ทำ Flow-ขั้นตอนการสรรหา.xlsx ของฝ่ายบุคคลให้เดินใน Odoo:

1. แผนกขออัตรา (ทดแทน / เพิ่มใหม่) ด้วยใบขออัตรากำลัง
2. ผู้จัดการฝ่ายอนุมัติ — อัตราเพิ่มใหม่ต้องผ่านสายงาน/รองกรรมการ/กรรมการอีกขั้น
   ผู้อนุมัติหาจากผังองค์กรเอง (ฝ่าย/สายงานของแผนก) ไม่อนุมัติ = กลับไปแก้ส่งใหม่
3. HR รับเรื่อง → เปิดรับสมัคร (รวมหน้าเว็บ /jobs) ผู้อนุมัติเห็นผู้สมัครของตำแหน่งนั้น
4. ผู้สมัคร: ใหม่ → คัดกรอง → สัมภาษณ์ → ประเมินผล → รออนุมัติจ้าง → นัดเริ่มงาน → เริ่มงานแล้ว
   ด่านรออนุมัติจ้างผ่านได้เมื่อสายงาน/กรรมการกดอนุมัติเท่านั้น
5. "เริ่มงาน" สร้างพนักงาน + สัญญาร่าง แล้วแจ้งแผนกให้กดรับทราบ
""",
    "version": "18.0.1.3.0",
    "license": "LGPL-3",
    "author": "Autozone IT",
    "category": "Autozone/HR",
    "depends": [
        "hr_recruitment",
        "website_hr_recruitment",
        "autozone_org_chart",      # division_id / line_id on departments, headcount plan on jobs
        "autozone_hr_blacklist",   # blacklist gate on applicants and new employees
        "autozone_hr_employee",    # hr.contract.term_type, probation_days, printed contracts
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "wizard/reject_wizard_views.xml",
        "views/manpower_request_views.xml",
        "views/hr_applicant_views.xml",
        "views/hr_candidate_views.xml",
        "views/website_templates.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "auto_install": False,
    "application": False,
}
