from odoo import api, fields, models
from odoo.exceptions import UserError


class AzSkuReissue(models.TransientModel):
    """Re-issue (new number) or cancel (no SKU, tick 'ไม่ออก SKU') a product's SKU."""
    _name = "az.sku.reissue"
    _description = "ออกรหัส SKU ใหม่ / ยกเลิก SKU"

    mode = fields.Selection([("reissue", "ออกรหัสใหม่"), ("cancel", "ยกเลิก SKU")],
                            default="reissue", required=True, readonly=True)
    product_tmpl_id = fields.Many2one("product.template", "สินค้า", required=True, readonly=True)
    old_sku = fields.Char(related="product_tmpl_id.az_sku", string="SKU ปัจจุบัน")
    label_printed = fields.Boolean(related="product_tmpl_id.az_sku_label_printed")
    new_prefix = fields.Char("หมวด+แบรนด์ที่จะใช้", compute="_compute_new_prefix")
    prefix_note = fields.Char(compute="_compute_new_prefix")
    reason = fields.Char("เหตุผล", required=True,
                         help="เช่น จัดหมวดผิด / ใส่แบรนด์ผิด / สินค้านี้ไม่ต้องมี SKU")

    @api.depends("product_tmpl_id", "mode")
    def _compute_new_prefix(self):
        for wiz in self:
            if wiz.mode == "cancel":
                wiz.new_prefix = False
                wiz.prefix_note = False
                continue
            prefix, why = wiz.product_tmpl_id._az_sku_prefix()
            wiz.new_prefix = prefix
            if not prefix:
                wiz.prefix_note = why
            elif wiz.old_sku and wiz.old_sku[:7] == prefix:
                wiz.prefix_note = ("หมวดและแบรนด์ยังเหมือนเดิม — รหัสใหม่จะต่างแค่เลขลำดับ "
                                   "ตรวจว่าแก้หมวด/แบรนด์ในสินค้าแล้วหรือยัง")
            else:
                wiz.prefix_note = False

    def action_confirm(self):
        self.ensure_one()
        if not self.env.user.has_group("custom_product_sku.group_sku_manager"):
            raise UserError("เฉพาะผู้ดูแลรหัสสินค้า (SKU) เท่านั้น")
        tmpl = self.product_tmpl_id
        if self.mode == "cancel":
            old = tmpl._az_sku_retire("cancel", self.reason, exclude=True)
            tmpl.message_post(body=f"ยกเลิก SKU {old or '-'} (ติ๊ก 'ไม่ออก SKU') เหตุผล: {self.reason}")
            return {"type": "ir.actions.act_window_close"}
        if not self.new_prefix:
            raise UserError(self.prefix_note)
        old = tmpl._az_sku_retire("retire", self.reason)
        tmpl._az_issue_sku(reason=f"ออกรหัสใหม่แทน {old}: {self.reason}" if old else self.reason)
        tmpl.message_post(body=f"ออกรหัส SKU ใหม่ {old or '-'} → {tmpl.az_sku or '-'} เหตุผล: {self.reason}")
        return {"type": "ir.actions.act_window_close"}
