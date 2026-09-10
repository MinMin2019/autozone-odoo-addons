# -*- coding: utf-8 -*-
"""เติมเลข/วันที่ใบกำกับภาษีซื้อ (แท็บ Tax Invoice ของ l10n_th_account_tax) อัตโนมัติ

- เลขใบกำกับ  ← Bill Reference (ref)
- วันที่ใบกำกับ ← Bill Date (invoice_date)

กติกา: เติมเฉพาะช่องที่ว่าง หรือช่องที่เคยเติมให้แล้วยังไม่ถูกแก้มือ (flag az_auto_*)
ค่าที่เติมให้จะเปลี่ยนตาม/ลบตามเมื่อ Bill Reference หรือ Bill Date เปลี่ยนหรือถูกลบ
ช่องที่บัญชีพิมพ์เองจะไม่ถูกทับและไม่ถูกลบ และถ้า Bill Reference ว่าง ระบบเดิมยังเตือน
"Please fill in tax invoice and tax date" ตอน Confirm เหมือนเดิม
"""
from dateutil.relativedelta import relativedelta

from odoo import api, models

PURCHASE_TYPES = ("in_invoice", "in_refund")
# ฟิลด์ที่เมื่อถูก write แล้วควรลองเติมใหม่ (บรรทัดภาษี/แถว tax invoice อาจเพิ่งเกิด)
AUTOFILL_TRIGGERS = {"ref", "invoice_date", "line_ids", "invoice_line_ids", "tax_invoice_ids"}


class AccountMove(models.Model):
    _inherit = "account.move"

    def _az_report_late_mo(self, tax_invoice_date):
        """คำนวณ Report Late แบบเดียวกับ _onchange_tax_invoice_date ของ l10n_th_account_tax
        (onchange ไม่ทำงานเมื่อเซ็ตค่าจากโค้ด จึงต้องคำนวณเอง)"""
        self.ensure_one()
        if not tax_invoice_date or not self.date:
            return "0"
        diff = relativedelta(self.date.replace(day=1), tax_invoice_date.replace(day=1))
        if diff.years > 0 or (diff.years == 0 and diff.months >= 6) or diff.months < 0:
            return "0"
        return str(diff.months)

    def _az_autofill_purchase_tax_invoice(self):
        for move in self:
            if move.move_type not in PURCHASE_TYPES or move.state != "draft":
                continue
            for tinv in move.tax_invoice_ids:
                if tinv.payment_id:  # ภาษี cash basis ฝั่ง payment ไม่เกี่ยว
                    continue
                # ลบ Bill Reference / Bill Date ออก → ค่าที่เคยเติมให้ (ยังไม่แก้มือ) ลบตาม
                if not move.ref and tinv.az_auto_number and tinv.tax_invoice_number:
                    tinv.tax_invoice_number = False
                if not move.invoice_date and tinv.az_auto_date and tinv.tax_invoice_date:
                    tinv.tax_invoice_date = False
                    tinv.report_late_mo = "0"
                if (
                    move.ref
                    and (not tinv.tax_invoice_number or tinv.az_auto_number)
                    and tinv.tax_invoice_number != move.ref
                ):
                    tinv.tax_invoice_number = move.ref
                    tinv.az_auto_number = True
                if (
                    move.invoice_date
                    and (not tinv.tax_invoice_date or tinv.az_auto_date)
                    and tinv.tax_invoice_date != move.invoice_date
                ):
                    tinv.tax_invoice_date = move.invoice_date
                    tinv.az_auto_date = True
                    tinv.report_late_mo = move._az_report_late_mo(move.invoice_date)

    # --- ฟอร์ม: พิมพ์ Bill Reference / Bill Date แล้วเห็นในแท็บทันที ---
    @api.onchange("ref", "invoice_date")
    def _onchange_az_autofill_tax_invoice(self):
        self._az_autofill_purchase_tax_invoice()

    # --- เซิร์ฟเวอร์: กันเคสสร้างจาก PO / import / API ที่ไม่ผ่าน onchange ---
    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._az_autofill_purchase_tax_invoice()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if AUTOFILL_TRIGGERS & set(vals):
            self._az_autofill_purchase_tax_invoice()
        return res

    def _post(self, soft=True):
        # เติมก่อนให้ l10n_th_account_tax ตรวจว่ามีเลข/วันที่ครบ
        self._az_autofill_purchase_tax_invoice()
        return super()._post(soft=soft)
