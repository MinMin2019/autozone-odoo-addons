# -*- coding: utf-8 -*-
"""ผูก Account Group กลับไปหาบัญชีหัวข้อ (Type View) ในผังแม่ที่สร้างมันขึ้นมา

ช่วงเลขของกลุ่ม (เช่น "51") เป็นแค่ตัวจับบัญชีเข้ากลุ่ม ไม่ใช่รหัสบัญชีจริง
เก็บลิงก์ไว้เพื่อให้หัวกลุ่มในรายงานโชว์เลขบัญชีเต็มของหัวข้อได้ (510000)
และเผื่อกรณีที่ prefix ไม่ตรงกับเลขบัญชีตรง ๆ (800000 ใช้ช่วง "81")
"""

from odoo import fields, models


class AccountGroup(models.Model):
    _inherit = "account.group"

    az_source_account_id = fields.Many2one(
        "account.account",
        string="บัญชีหัวข้อในผังแม่",
        ondelete="set null",
        help="บัญชี Type View ที่กลุ่มนี้ถูกสร้างขึ้นมาจาก — "
        "ใช้แสดงเลขบัญชีเต็มที่หัวกลุ่มในรายงาน",
    )
