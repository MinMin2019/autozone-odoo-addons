from odoo import api, fields, models
from odoo.exceptions import UserError

# (ชื่อฟิลด์จำนวน, มูลค่าต่อหน่วย, ป้ายบนฟอร์ม)
DENOMINATIONS = [
    ("qty_1000", 1000.0, "ธนบัตร 1,000 บาท"),
    ("qty_500", 500.0, "ธนบัตร 500 บาท"),
    ("qty_100", 100.0, "ธนบัตร 100 บาท"),
    ("qty_50", 50.0, "ธนบัตร 50 บาท"),
    ("qty_20", 20.0, "ธนบัตร 20 บาท"),
    ("qty_10", 10.0, "เหรียญ 10 บาท"),
    ("qty_5", 5.0, "เหรียญ 5 บาท"),
    ("qty_2", 2.0, "เหรียญ 2 บาท"),
    ("qty_1", 1.0, "เหรียญ 1 บาท"),
]


class PettyCashCount(models.Model):
    _name = "petty.cash.count"
    _description = "ใบนับเงินสดย่อย (Cash Count)"
    _inherit = ["mail.thread", "petty.cash.document"]
    _order = "date desc, name desc"

    fund_id = fields.Many2one(
        "petty.cash.fund", string="กองเงินสดย่อย", required=True,
        tracking=True, index=True)
    company_id = fields.Many2one(related="fund_id.company_id", store=True)
    currency_id = fields.Many2one(related="fund_id.currency_id")
    date = fields.Date(
        string="วันที่นับ", required=True,
        default=fields.Date.context_today, tracking=True)
    counter_name = fields.Char(string="ผู้นับเงิน", required=True)
    witness_name = fields.Char(string="ผู้ร่วมนับ/พยาน")

    qty_1000 = fields.Integer(string="ธนบัตร 1,000")
    qty_500 = fields.Integer(string="ธนบัตร 500")
    qty_100 = fields.Integer(string="ธนบัตร 100")
    qty_50 = fields.Integer(string="ธนบัตร 50")
    qty_20 = fields.Integer(string="ธนบัตร 20")
    qty_10 = fields.Integer(string="เหรียญ 10")
    qty_5 = fields.Integer(string="เหรียญ 5")
    qty_2 = fields.Integer(string="เหรียญ 2")
    qty_1 = fields.Integer(string="เหรียญ 1")
    amount_satang = fields.Monetary(string="เศษสตางค์/อื่น ๆ")

    counted_amount = fields.Monetary(
        string="ยอดนับได้จริง", compute="_compute_counted", store=True)
    expected_amount = fields.Monetary(
        string="ยอดตามทะเบียน", readonly=True, copy=False,
        help="ยอดเงินคงเหลือในกองตามทะเบียน ณ ตอนสร้าง/ยืนยันเอกสาร "
        "(ปุ่ม 'ดึงยอดทะเบียน' อัปเดตใหม่ได้ขณะยังเป็นร่าง)")
    fund_balance_now = fields.Monetary(
        related="fund_id.balance", string="ยอดทะเบียนปัจจุบัน")
    difference = fields.Monetary(
        string="ผลต่าง (นับได้ − ทะเบียน)", compute="_compute_counted", store=True,
        help="บวก = เงินเกิน, ลบ = เงินขาด")
    note = fields.Text(string="หมายเหตุ/คำอธิบายผลต่าง")
    state = fields.Selection(
        [("draft", "ร่าง"), ("done", "ยืนยันแล้ว"), ("cancel", "ยกเลิก")],
        default="draft", tracking=True, copy=False)

    @api.depends("qty_1000", "qty_500", "qty_100", "qty_50", "qty_20",
                 "qty_10", "qty_5", "qty_2", "qty_1", "amount_satang",
                 "expected_amount")
    def _compute_counted(self):
        for rec in self:
            total = sum(rec[f] * value for f, value, _label in DENOMINATIONS)
            rec.counted_amount = total + rec.amount_satang
            rec.difference = rec.counted_amount - rec.expected_amount

    @api.onchange("fund_id")
    def _onchange_fund_id(self):
        if self.fund_id and self.state == "draft":
            self.expected_amount = self.fund_id.balance

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # เลขที่เอกสารออกให้โดย mixin petty.cash.document
            if "expected_amount" not in vals and vals.get("fund_id"):
                vals["expected_amount"] = (
                    self.env["petty.cash.fund"].browse(vals["fund_id"]).balance)
        return super().create(vals_list)

    def action_refresh_expected(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError("ดึงยอดทะเบียนได้เฉพาะเอกสารร่าง")
            rec.expected_amount = rec.fund_id.balance

    def action_done(self):
        for rec in self:
            if rec.state != "draft":
                continue
            if rec.difference and not rec.note:
                raise UserError(
                    "ยอดนับได้ไม่ตรงทะเบียน (ผลต่าง %.2f) "
                    "กรุณาใส่คำอธิบายในช่องหมายเหตุก่อนยืนยัน" % rec.difference)
            rec.state = "done"

    def action_cancel(self):
        self.state = "cancel"

    def action_reset_draft(self):
        for rec in self:
            if rec.state != "cancel":
                raise UserError("Reset ได้เฉพาะเอกสารที่ยกเลิกแล้ว")
            rec.state = "draft"

    def unlink(self):
        if any(r.state == "done" for r in self):
            raise UserError("ลบเอกสารที่ยืนยันแล้วไม่ได้ (ยกเลิกก่อน)")
        return super().unlink()

    def get_denomination_rows(self):
        """แถวตารางแตกชนิดเงินสำหรับฟอร์มพิมพ์: (ป้าย, จำนวน, มูลค่า, รวม)"""
        self.ensure_one()
        return [
            (label, self[f], value, self[f] * value)
            for f, value, label in DENOMINATIONS
        ]
