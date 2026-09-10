# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMoveTaxInvoice(models.Model):
    _inherit = "account.move.tax.invoice"

    # flag บอกว่าค่าในช่องมาจากการเติมอัตโนมัติ (ยังไม่ถูกบัญชีแก้มือ)
    # ถ้า True → เมื่อ Bill Reference / Bill Date เปลี่ยน ค่าจะเปลี่ยนตาม
    # ถ้า False → บัญชีพิมพ์เอง ระบบจะไม่ทับ
    az_auto_number = fields.Boolean(
        string="Number Auto-filled", default=False, copy=False,
        help="เลขใบกำกับถูกเติมจาก Bill Reference อัตโนมัติ และจะเปลี่ยนตามเมื่อแก้ Bill Reference",
    )
    az_auto_date = fields.Boolean(
        string="Date Auto-filled", default=False, copy=False,
        help="วันที่ใบกำกับถูกเติมจาก Bill Date อัตโนมัติ และจะเปลี่ยนตามเมื่อแก้ Bill Date",
    )

    @api.onchange("tax_invoice_number")
    def _onchange_az_tax_invoice_number(self):
        # บัญชีแก้เลขเอง → เลิกตาม Bill Reference (ยกเว้นพิมพ์ค่าเดียวกับ ref พอดี)
        for rec in self:
            rec.az_auto_number = bool(rec.tax_invoice_number) and (
                rec.tax_invoice_number == rec.move_id.ref
            )

    @api.onchange("tax_invoice_date")
    def _onchange_az_tax_invoice_date(self):
        for rec in self:
            rec.az_auto_date = bool(rec.tax_invoice_date) and (
                rec.tax_invoice_date == rec.move_id.invoice_date
            )
