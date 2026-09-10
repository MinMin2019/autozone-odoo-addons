from odoo import models

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _prepare_invoice(self):
        # สร้างบิลผ่านปุ่ม Create Bill จาก PO: ใส่เลขที่ PO ลงช่อง PO No. ให้อัตโนมัติ
        # (บิลที่สร้างเองตรงๆ ยังคีย์ x_po_number เองตามเดิม)
        vals = super()._prepare_invoice()
        vals['x_po_number'] = self.name
        return vals

    def action_create_invoice(self):
        # กรณีเลือกหลาย PO แล้วรวมเป็นบิลใบเดียว: ต่อเลข PO ทุกใบ เช่น "PO001, PO002"
        # (_prepare_invoice ใส่ได้แค่เลขของ PO ใบแรกของกลุ่ม)
        before = self.invoice_ids
        res = super().action_create_invoice()
        for move in (self.invoice_ids - before):
            orders = move.line_ids.mapped('purchase_line_id.order_id')
            if len(orders) > 1:
                move.x_po_number = ', '.join(orders.sorted('name').mapped('name'))
        return res
