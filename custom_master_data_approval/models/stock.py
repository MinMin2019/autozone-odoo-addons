from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        # ต้อง hook ที่ _action_done ไม่ใช่ button_validate — custom_stock_backdate
        # (และโค้ดโปรแกรมอื่น) เรียก _action_done ตรงโดยข้ามปุ่ม Validate
        Check = self.env["az.approval.type"]
        for picking in self:
            if picking.partner_id:
                Check.check_partners(
                    picking.partner_id, "ยืนยันใบโอน %s" % picking.name)
        return super()._action_done()


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        # ด่านฝั่งสินค้า: ครอบทุกใบโอน + เบิกใช้ CONS + inventory adjustment
        # + move ที่เกิดโดยไม่มี picking
        products = self.mapped("product_id")
        if products:
            self.env["az.approval.type"].check_products(products, "ตัดสต็อก")
        return super()._action_done(cancel_backorder=cancel_backorder)
