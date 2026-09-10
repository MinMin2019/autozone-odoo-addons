from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    # ใช้ร่วมกันทั้ง รับ (RV) และ จ่าย (PV)
    x_cheque_number = fields.Char(string="Cheque No.")

    # เฉพาะ จ่าย (PV)
    x_payment_date = fields.Date(string="Payment Date")

    # เฉพาะ รับ (RV)
    x_receipt_date = fields.Date(string="Receipt Date")

    # เฉพาะ ทั่วไป (JV): รายละเอียดรายการ แสดงในรายงานใบสำคัญทั่วไป
    x_description = fields.Char(string="Description")

    # เฉพาะ Vendor Bill: เลขที่ PO คีย์เอง แสดงเป็น อ้างถึง/Ref. ในใบสำคัญการตั้งหนี้
    x_po_number = fields.Char(string="PO No.")

    x_journal_code = fields.Char(related='journal_id.code', string="Journal Code", store=True)

    # จำนวนแถวต่อหน้าของรายงานใบสำคัญ (แถวสูงคงที่ 58px — เลขตายตัว
    # คาลิเบรตจากการ render จริง, ดู memory: thai-vouchers-report-spec)
    VOUCHER_ROWS_CONT = 20   # หน้าที่ยังไม่จบ (ไม่มียอดรวม/ลายเซ็น)
    VOUCHER_ROWS_LAST = 16   # หน้าสุดท้าย (มีแถวยอดรวม+ช่องลายเซ็น)

    def _get_voucher_line_pages(self):
        """แบ่งบรรทัดรายการเป็นหน้าๆ สำหรับรายงานใบสำคัญ (แถวสูงคงที่)

        ลำดับรายการ: ฝั่งเดบิตเรียงยอดมาก->น้อย, ภาษีซื้อไปท้ายสุดของฝั่งเดบิต
        (ธรรมเนียมใบสำคัญ: ฐานภาษีก่อน แล้วปิดฝั่งเดบิตด้วยภาษีซื้อ), แล้วจึงเครดิต

        แบ่งแบบ fill-front: หน้าที่ยังไม่จบใส่ ROWS_CONT แถว, หน้าสุดท้าย
        ไม่เกิน ROWS_LAST และมีรายการอย่างน้อย 1 แถวเสมอ
        (ไม่มีหน้าที่มีแต่ลายเซ็นเปล่าๆ)
        """
        self.ensure_one()

        def sort_key(l):
            is_credit = 0 if l.debit else 1
            is_vat = 1 if (l.account_id.name or '').startswith('ภาษีซื้อ') else 0
            return (is_credit, is_vat, -l.debit)

        # ไม่พิมพ์บรรทัดที่เดบิต=0 และเครดิต=0 ทั้งคู่ (เศษ "บรรทัดปรับสมดุลอัตโนมัติ"/
        # บรรทัดภาษีที่ถูกล้างค่า ซึ่ง odoo ทิ้งไว้ตอนแก้ไขเอกสาร — ไม่มีผลทางบัญชี)
        lines = [l for l in self.line_ids.sorted(key=sort_key)
                 if l.debit or l.credit]
        cont, last = self.VOUCHER_ROWS_CONT, self.VOUCHER_ROWS_LAST

        if len(lines) <= last:
            return [lines]

        pages, i, n = [], 0, len(lines)
        while n - i > last:
            take = min(cont, n - i - 1)   # กันหน้าสุดท้ายว่าง: เหลืออย่างน้อย 1 แถว
            pages.append(lines[i:i + take])
            i += take
        pages.append(lines[i:])
        return pages
