from odoo import api, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    @api.depends("order_line.date_planned")
    def _compute_date_planned(self):
        # ค่าที่ user ตั้งไว้บนหัว PO ต้องไม่ถูก min ของบรรทัดทับ
        # (ตอนเพิ่มบรรทัดแรก บรรทัดยังอ่านวันหัวไม่ได้ จะได้ lead time = วันนี้
        # แล้ว compute ตัวนี้จะเอาวันนี้มาทับวันที่พิมพ์ไว้)
        manual = self.filtered("date_planned")
        for order in manual:
            order.date_planned = order.date_planned
        super(PurchaseOrder, self - manual)._compute_date_planned()
