# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # คำนำหน้าชื่อ (นาย/นาง/นางสาว/Mr./Miss ฯลฯ) แยกจาก name เพื่อให้ avatar/การค้นหา
    # ใช้ชื่อจริง ส่วนเอกสารทางการประกอบเป็น "คำนำหน้า + ชื่อ" ได้
    title_th = fields.Char(string='คำนำหน้า', tracking=True)

    # ระดับตำแหน่งตามโครงสร้างองค์กรใหม่ (G2-G5, S2-S4, SC, M1, P2, TM1-TM2)
    # เก็บเป็น Char เพราะโครงสร้างยังไม่ final
    job_level = fields.Char(string='ระดับตำแหน่ง (Job Level)', tracking=True)

    # เพิ่มระดับวุฒิการศึกษาแบบไทยตามข้อมูลจริงของบริษัท
    # (แทรกก่อน Graduate เพื่อให้ dropdown เรียงจากต่ำไปสูง)
    certificate = fields.Selection(
        selection_add=[
            ('primary_3', 'ประถมศึกษาปีที่ 3 (ป.3)'),
            ('primary_6', 'ประถมศึกษาปีที่ 6 (ป.6)'),
            ('secondary_3', 'มัธยมศึกษาปีที่ 3 (ม.3)'),
            ('secondary_6', 'มัธยมศึกษาปีที่ 6 (ม.6)'),
            ('nfe', 'กศน. (การศึกษานอกระบบ)'),
            ('vocational_cert', 'ปวช.'),
            ('technical_cert', 'ปวท.'),
            ('high_vocational', 'ปวส.'),
            ('graduate',),
        ],
        ondelete={
            'primary_3': 'set null',
            'primary_6': 'set null',
            'secondary_3': 'set null',
            'secondary_6': 'set null',
            'nfe': 'set null',
            'vocational_cert': 'set null',
            'technical_cert': 'set null',
            'high_vocational': 'set null',
        },
    )
