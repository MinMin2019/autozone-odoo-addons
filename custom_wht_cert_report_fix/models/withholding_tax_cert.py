from odoo import models


class WithholdingTaxCert(models.Model):
    _inherit = "withholding.tax.cert"

    def action_done(self):
        # ใช้เลขใบจ่ายเงิน/JE (ฟิลด์ name) เป็นเลขที่หนังสือรับรองแทน sequence กลาง
        # ตั้งก่อนเรียก super เพื่อให้ super ข้ามการออกเลขจาก sequence (ออกเฉพาะตอน number == "/")
        for rec in self:
            if rec.number == "/" and rec.name:
                number = rec.name
                # กันเลขซ้ำกรณีใบจ่ายเดียวกันมีใบรับรอง active มากกว่าหนึ่งใบ
                # (ยกเว้นใบเดิมที่กำลังถูกแทนที่ ซึ่ง super จะ cancel ให้ — ใบใหม่ใช้เลขเดิมได้)
                dup = self.search_count(
                    [
                        ("number", "=", number),
                        ("state", "!=", "cancel"),
                        ("id", "not in", [rec.id, rec.ref_wht_cert_id.id]),
                    ]
                )
                if dup:
                    number = "%s-%s" % (number, dup + 1)
                rec.number = number
        return super().action_done()
