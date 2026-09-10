from odoo import api, fields, models
from odoo.exceptions import UserError


class PettyCashRequest(models.Model):
    _name = "petty.cash.request"
    _description = "ใบเบิกเงินสดย่อย"
    _inherit = ["mail.thread", "petty.cash.document"]
    _order = "date desc, name desc"

    fund_id = fields.Many2one(
        "petty.cash.fund", string="กองเงินสดย่อย", required=True,
        tracking=True, index=True)
    company_id = fields.Many2one(related="fund_id.company_id", store=True)
    currency_id = fields.Many2one(related="fund_id.currency_id")
    date = fields.Date(
        string="วันที่เบิก (ตามเอกสารสาขา)", required=True,
        default=fields.Date.context_today, tracking=True)
    requester_name = fields.Char(string="ผู้ขอเบิก", required=True, tracking=True)
    amount = fields.Monetary(string="จำนวนเงิน", required=True, tracking=True)
    purpose = fields.Char(string="วัตถุประสงค์", required=True)
    note = fields.Text(string="หมายเหตุ")
    state = fields.Selection(
        [
            ("draft", "ร่าง"),
            ("paid", "จ่ายเงินแล้ว"),
            ("cleared", "เคลียร์แล้ว"),
            ("cancel", "ยกเลิก"),
        ],
        default="draft", tracking=True, copy=False,
    )
    clearing_id = fields.Many2one(
        "petty.cash.clearing", string="ใบเคลียร์", readonly=True, copy=False)

    def action_confirm(self):
        over = []
        for req in self:
            if req.state != "draft":
                continue
            balance_before = req.fund_id.balance
            req.state = "paid"
            if req.amount > balance_before:
                over.append(
                    f"{req.name}: เบิก {req.amount:,.2f} แต่กอง {req.fund_id.code} "
                    f"มีเงินคงเหลือตามทะเบียนเพียง {balance_before:,.2f}")
        if over:
            # เตือนแต่ไม่บล็อก — บัญชีคีย์ตามเหตุการณ์จริงย้อนหลัง
            # ถ้าสาขาเบิกเกินไปแล้วจริงก็ต้องบันทึกได้ แต่ควรรู้ว่ายอดกองติดลบ
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "เบิกเกินเงินคงเหลือในกอง",
                    "message": "\n".join(over)
                    + "\nบันทึกให้แล้ว — ตรวจสอบกับสาขาว่าเงินในกล่องพอจริงหรือไม่",
                    "type": "warning",
                    "sticky": True,
                },
            }

    def action_cancel(self):
        for req in self:
            if req.state == "cleared":
                raise UserError("ใบเบิกที่เคลียร์แล้วยกเลิกไม่ได้ ให้ยกเลิกใบเคลียร์ก่อน")
            req.state = "cancel"

    def action_reset_draft(self):
        for req in self:
            if req.state == "cleared":
                raise UserError("ใบเบิกที่เคลียร์แล้วแก้ไม่ได้ ให้ยกเลิกใบเคลียร์ก่อน")
            req.state = "draft"

    def unlink(self):
        if any(r.state not in ("draft", "cancel") for r in self):
            raise UserError("ลบได้เฉพาะใบเบิกสถานะร่าง/ยกเลิก")
        return super().unlink()
