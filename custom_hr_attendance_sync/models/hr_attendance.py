# -*- coding: utf-8 -*-
from odoo import fields, models


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    az_source = fields.Selection(
        [('bpcontrol', 'เครื่องสแกนนิ้ว (BpControl)')],
        string='ที่มาของข้อมูล', readonly=True, index=True,
        help='ว่างไว้ = คีย์เอง/Kiosk; bpcontrol = ดึงมาจากเครื่องสแกนนิ้วอัตโนมัติ')
    az_source_key = fields.Char(
        string='รหัสอ้างอิงต้นทาง', readonly=True, index=True,
        help='สาขา|รหัสพนักงาน|วันที่|ช่วง — ใช้กันข้อมูลซ้ำเวลาดึงรอบใหม่')
    az_scan_date = fields.Date(
        string='วันที่สแกน', readonly=True, index=True,
        help='วันที่ตามฝั่งเครื่องสแกน (เวลาไทย) ไม่ใช่วันที่ของ check_in ที่เป็น UTC')
