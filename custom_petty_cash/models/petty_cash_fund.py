from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PettyCashFund(models.Model):
    _name = "petty.cash.fund"
    _description = "กองเงินสดย่อย (Petty Cash Fund)"
    _order = "code, id"

    name = fields.Char(string="ชื่อกอง", required=True)
    code = fields.Char(string="รหัสสาขา", required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda self: self.env.company, required=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    amount_limit = fields.Monetary(string="วงเงิน", default=4000.0, required=True)
    journal_id = fields.Many2one(
        "account.journal", string="Journal เงินสดสาขา",
        domain="[('type', '=', 'cash')]", required=True,
        help="Journal เงินสดย่อยประจำสาขา ใช้จ่าย vendor bill (register payment)",
    )
    bill_journal_id = fields.Many2one(
        "account.journal", string="Journal ตั้งหนี้",
        domain="[('type', '=', 'purchase')]", required=True,
        help="Journal สำหรับ draft vendor bill ที่สร้างจากใบเคลียร์ "
        "(แยกจากบิลการค้าปกติเพื่อให้กรองง่าย)",
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="Analytic สาขา", required=True,
        help="ใส่ analytic distribution ให้ทุกบรรทัดของ vendor bill อัตโนมัติ",
    )
    # ผู้ถือ/ผู้อนุมัติทำงานบนกระดาษที่สาขา ไม่มี login → เก็บเป็นชื่อไว้แสดงบนฟอร์ม
    custodian_name = fields.Char(string="ผู้ถือเงิน (ธุรการสาขา)")
    approver_name = fields.Char(string="ผู้อนุมัติ (ผู้จัดการสาขา)")

    request_ids = fields.One2many("petty.cash.request", "fund_id")
    clearing_ids = fields.One2many("petty.cash.clearing", "fund_id")

    balance = fields.Monetary(
        string="เงินคงเหลือในกอง", compute="_compute_balance",
        help="วงเงิน − ใบเบิกที่ยังไม่เคลียร์ − ยอดใช้จ่ายที่เคลียร์แล้วแต่ยังไม่ได้เติมเงิน",
    )
    open_request_amount = fields.Monetary(
        string="เบิกค้างเคลียร์", compute="_compute_balance")
    unreplenished_amount = fields.Monetary(
        string="รอเติมเงิน", compute="_compute_balance")

    _sql_constraints = [
        ("code_company_uniq", "unique(code, company_id)", "รหัสสาขาซ้ำ"),
    ]

    @api.constrains("journal_id")
    def _check_journal_outstanding(self):
        # journal ที่ outstanding ว่าง กด Pay แล้วจะไม่เกิดรายการบัญชีแบบเงียบ ๆ
        # ต้องดักตั้งแต่ตอนผูกกับกอง ไม่ใช่ไปเจอตอนเงินหาย
        for fund in self:
            outbound = fund.journal_id.outbound_payment_method_line_ids
            if not outbound.filtered("payment_account_id"):
                raise ValidationError(
                    f"Journal {fund.journal_id.display_name} ยังไม่ได้ตั้ง "
                    "Outstanding Payments Account — ผูกกับกองไม่ได้ "
                    "เพราะกดจ่ายเงินแล้วจะไม่เกิดรายการบัญชี\n\n"
                    "วิธีแก้: Accounting → Configuration → Journals → เปิด journal นี้ → "
                    "แท็บ Outgoing Payments บรรทัด Manual → ตั้ง Outstanding Payments Account "
                    "= 111001 (บัญชีพักเงินจ่าย) แล้วกลับมาบันทึกกองใหม่"
                )

    @api.depends("amount_limit", "request_ids.state", "request_ids.amount",
                 "clearing_ids.state", "clearing_ids.amount_spent")
    def _compute_balance(self):
        for fund in self:
            open_req = sum(
                fund.request_ids.filtered(lambda r: r.state == "paid").mapped("amount")
            )
            unrep = sum(
                fund.clearing_ids.filtered(lambda c: c.state == "billed").mapped("amount_spent")
            )
            fund.open_request_amount = open_req
            fund.unreplenished_amount = unrep
            fund.balance = fund.amount_limit - open_req - unrep

    @api.depends("code", "name")
    def _compute_display_name(self):
        for fund in self:
            fund.display_name = f"[{fund.code}] {fund.name}" if fund.code else fund.name
