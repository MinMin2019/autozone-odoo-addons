from odoo import api, fields, models
from odoo.exceptions import UserError


class PettyCashReplenish(models.Model):
    _name = "petty.cash.replenish"
    _description = "ใบสรุปขอเติมเงินสดย่อย"
    _inherit = ["mail.thread", "petty.cash.document"]
    _order = "date desc, name desc"

    fund_id = fields.Many2one(
        "petty.cash.fund", string="กองเงินสดย่อย", required=True,
        tracking=True, index=True)
    company_id = fields.Many2one(related="fund_id.company_id", store=True)
    currency_id = fields.Many2one(related="fund_id.currency_id")
    date = fields.Date(
        string="วันที่", required=True,
        default=fields.Date.context_today, tracking=True)
    clearing_ids = fields.One2many(
        "petty.cash.clearing", "replenish_id", string="ใบเคลียร์ที่รวมเติมเงิน",
        # ใช้คู่กับ widget="many2many" ใน view: ปุ่ม Add = เลือกใบเคลียร์ที่มีอยู่
        # (ไม่ใช่สร้างใหม่) — กรองเฉพาะกองเดียวกัน สร้างบิลแล้ว และยังไม่ถูกใบเติมเงินอื่นจอง
        domain="[('fund_id', '=', fund_id), ('state', '=', 'billed'),"
        " ('replenish_id', '=', False)]")
    amount_total = fields.Monetary(
        string="ยอดขอเติมเงิน", compute="_compute_amount", store=True)
    transfer_ref = fields.Char(
        string="อ้างอิงรายการโอน/JE",
        help="เลขที่ internal transfer หรือ JE ที่ฝ่ายบัญชีบันทึกการเติมเงิน")
    note = fields.Text(string="หมายเหตุ")
    state = fields.Selection(
        [("draft", "ร่าง"), ("done", "เติมเงินแล้ว"), ("cancel", "ยกเลิก")],
        default="draft", tracking=True, copy=False)

    @api.depends("clearing_ids.amount_spent")
    def _compute_amount(self):
        for rec in self:
            rec.amount_total = sum(rec.clearing_ids.mapped("amount_spent"))

    def action_done(self):
        for rec in self:
            if not rec.clearing_ids:
                raise UserError("ยังไม่ได้เลือกใบเคลียร์")
            unbilled = rec.clearing_ids.filtered(lambda c: c.state != "billed")
            if unbilled:
                raise UserError(
                    "ใบเคลียร์ต่อไปนี้ยังไม่อยู่ในสถานะสร้างบิลแล้ว: "
                    + ", ".join(unbilled.mapped("name")))
            rec.clearing_ids.state = "replenished"
            rec.state = "done"

    def action_cancel(self):
        for rec in self:
            rec.clearing_ids.filtered(
                lambda c: c.state == "replenished").state = "billed"
            rec.state = "cancel"

    def action_reset_draft(self):
        for rec in self:
            if rec.state != "cancel":
                raise UserError("Reset ได้เฉพาะเอกสารที่ยกเลิกแล้ว")
            rec.state = "draft"

    def unlink(self):
        if any(r.state == "done" for r in self):
            raise UserError("ลบเอกสารที่เติมเงินแล้วไม่ได้")
        return super().unlink()

    def get_expense_summary(self):
        """สรุปยอดตามหมวดบัญชี สำหรับฝ่ายบัญชีใช้ตรวจ/ลงรายการเติมเงิน

        รวมทั้งบรรทัดใบเสร็จ และบรรทัดของบิลตั้งหนี้ที่จ่ายด้วยเงินสดย่อย
        คืน list ของ dict: {account, untaxed, tax, total}
        """
        self.ensure_one()
        summary = {}

        def add(acc, untaxed, tax, total):
            row = summary.setdefault(
                acc.id, {"account": acc, "untaxed": 0.0, "tax": 0.0, "total": 0.0})
            row["untaxed"] += untaxed
            row["tax"] += tax
            row["total"] += total

        for line in self.clearing_ids.line_ids:
            add(line.expense_account_id, line.amount_untaxed,
                line.amount_tax, line.amount_total)
        for bill in self.clearing_ids.existing_bill_ids:
            # ใบลดหนี้กลับเครื่องหมาย ยอดตามหมวดบัญชีจึงลดลงตามจริง
            sign = self.env["petty.cash.clearing"]._bill_sign(bill)
            for inv_line in bill.invoice_line_ids:
                add(inv_line.account_id, sign * inv_line.price_subtotal,
                    sign * (inv_line.price_total - inv_line.price_subtotal),
                    sign * inv_line.price_total)
        return sorted(summary.values(), key=lambda r: r["account"].code or "")
