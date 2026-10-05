from odoo import models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _post_payments(self, to_process, edit_mode=False):
        # ส่ง "ใบรับเงินนี้รับเงินของเอกสารไหน" ไปถึงตอนตั้งเลข (การจับคู่จริงเกิดหลัง post)
        # ต้องใส่ context ที่ wizard เอง: core รวม payments ด้วย self.env['account.payment'] |= ...
        # ซึ่งใช้ env ของ wizard (context บน record payment จะหาย)
        doc_map = {vals['payment'].id: vals['to_reconcile'].move_id.ids for vals in to_process}
        return super(AccountPaymentRegister, self.with_context(az_receipt_docs=doc_map))._post_payments(
            to_process, edit_mode=edit_mode)
