from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class PettyCashClearing(models.Model):
    _name = "petty.cash.clearing"
    _description = "ใบเคลียร์เงินสดย่อย (ใบสำคัญจ่ายเงินสดย่อย)"
    _inherit = ["mail.thread", "petty.cash.document"]
    _order = "date desc, name desc"

    fund_id = fields.Many2one(
        "petty.cash.fund", string="กองเงินสดย่อย", required=True,
        tracking=True, index=True)
    company_id = fields.Many2one(related="fund_id.company_id", store=True)
    currency_id = fields.Many2one(related="fund_id.currency_id")
    date = fields.Date(
        string="วันที่เคลียร์", required=True,
        default=fields.Date.context_today, tracking=True)
    request_ids = fields.One2many(
        "petty.cash.request", "clearing_id", string="ใบเบิกที่เคลียร์",
        domain="[('fund_id', '=', fund_id), ('state', 'in', ('paid', 'cleared'))]")
    line_ids = fields.One2many(
        "petty.cash.clearing.line", "clearing_id", string="ใบเสร็จ", copy=True)
    existing_bill_ids = fields.Many2many(
        "account.move", "petty_clearing_existing_bill_rel", "clearing_id", "move_id",
        string="บิลตั้งหนี้/ใบลดหนี้ที่จ่ายด้วยเงินสดย่อย",
        domain="[('move_type', 'in', ('in_invoice', 'in_refund')), ('state', '=', 'posted'),"
        " ('payment_state', 'in', ('not_paid', 'partial')),"
        " ('petty_clearing_id', '=', False),"
        " ('petty_existing_clearing_ids', '=', False),"
        " ('company_id', '=', company_id)]",
        help="บิลที่ตั้งหนี้ไว้แล้วในระบบ (รวมบิลจาก PO) ซึ่งสาขาจ่ายด้วยเงินสดย่อย — "
        "ยอดจะนับเข้าทะเบียนกองและใบสรุปขอเติมเงิน\n"
        "ใบลดหนี้ของผู้ขายรายเดียวกันดึงเข้ามาพร้อมบิลได้ ยอดจะถูกหักออก "
        "และตอนกด Post + จ่ายทั้งชุด ระบบจะจ่ายเป็นยอดสุทธิก้อนเดียว")
    note = fields.Text(string="หมายเหตุ")
    state = fields.Selection(
        [
            ("draft", "ร่าง"),
            ("billed", "สร้างบิลแล้ว"),
            ("replenished", "เติมเงินแล้ว"),
            ("cancel", "ยกเลิก"),
        ],
        default="draft", tracking=True, copy=False,
    )
    replenish_id = fields.Many2one(
        "petty.cash.replenish", string="ใบขอเติมเงิน", readonly=True, copy=False)
    reimburse_ok = fields.Boolean(
        string="ยืนยันกรณีสำรองจ่าย", copy=False,
        help="ติ๊กเพื่อยืนยันว่าเคลียร์แบบไม่มีใบเบิก หรือยอดใช้จ่ายเกินยอดเบิก "
        "(สาขาสำรองจ่ายจริง ไม่ใช่ลืมดึงใบเบิก/คีย์ยอดผิด)")

    amount_advance = fields.Monetary(
        string="ยอดเบิก", compute="_compute_amounts", store=True)
    amount_existing = fields.Monetary(
        string="ยอดจ่ายบิลตั้งหนี้", compute="_compute_amount_existing", store=True,
        help="ยอดที่กองจ่ายให้บิลตั้งหนี้: ใบที่ยังไม่จ่าย/จ่ายบางส่วน = ยอดค้างชำระ, "
        "ใบที่จ่ายแล้ว = ยอดเต็มของบิล")
    amount_spent = fields.Monetary(
        string="ยอดใช้จ่ายจริง", compute="_compute_amounts", store=True,
        help="ใบเสร็จทั้งหมด + บิลตั้งหนี้ที่จ่ายด้วยเงินสดย่อย")
    amount_return = fields.Monetary(
        string="เงินทอนคืนกอง", compute="_compute_amounts", store=True,
        help="ยอดเบิก − ยอดใช้จ่ายจริง (ติดลบ = สาขาสำรองจ่ายเพิ่ม)")
    amount_wht_total = fields.Monetary(
        string="หัก ณ ที่จ่าย", compute="_compute_amount_wht_total",
        help="ยอด WHT รวมทั้งใบ (ใบเสร็จ + บิลตั้งหนี้ที่ดึงมา) — "
        "หักจริงตอนจ่าย เงินสดที่ออกจากกองจึงเป็นยอดใช้จ่ายจริงหักด้วยยอดนี้")
    amount_net_cash = fields.Monetary(
        string="เงินสดจ่ายสุทธิ", compute="_compute_amount_wht_total",
        help="ยอดใช้จ่ายจริง − หัก ณ ที่จ่าย = เงินสดที่ออกจากกองจริง")

    @api.depends("line_ids.amount_wht", "existing_bill_ids.petty_wht_amount",
                 "amount_spent")
    def _compute_amount_wht_total(self):
        for rec in self:
            rec.amount_wht_total = (
                sum(rec.line_ids.mapped("amount_wht"))
                + sum(rec._bill_sign(bill) * bill.petty_wht_amount
                      for bill in rec.existing_bill_ids))
            rec.amount_net_cash = rec.amount_spent - rec.amount_wht_total

    bill_ids = fields.One2many(
        "account.move", "petty_clearing_id", string="Vendor Bills")
    bill_count = fields.Integer(compute="_compute_bill_count")

    # ยอดที่กองจ่ายให้บิลแต่ละใบ: ยังไม่จ่าย/จ่ายบางส่วน = ยอดค้างชำระ,
    # จ่ายแล้ว = ยอดเต็มของบิล
    # (เดิมใช้ residual ล้วนแล้ว freeze ไว้ แต่พอ compute ถูกเรียกใหม่หลังจ่ายบิล
    #  residual เป็น 0 ยอดจึงหายไปทั้งชุด — เคส PCC2026/0015 เหลือ 924 จาก 17,223.18)
    # ใบลดหนี้ = ผู้ขายลดหนี้ให้ เงินสดออกจากกองน้อยลง จึงนับเป็นยอดติดลบทุกที่
    # (ทั้งยอดใช้จ่าย ยอด WHT ใบสรุปขอเติมเงิน และรายงาน)
    @staticmethod
    def _bill_sign(bill):
        return -1 if bill.move_type == "in_refund" else 1

    @classmethod
    def _bill_paid_by_fund(cls, bill):
        if bill.payment_state in ("not_paid", "partial"):
            amount = bill.amount_residual
        else:
            amount = bill.amount_total
        return cls._bill_sign(bill) * amount

    @api.depends("existing_bill_ids", "existing_bill_ids.payment_state",
                 "existing_bill_ids.amount_total",
                 "existing_bill_ids.amount_residual")
    def _compute_amount_existing(self):
        for rec in self:
            rec.amount_existing = sum(
                self._bill_paid_by_fund(bill) for bill in rec.existing_bill_ids)

    @api.depends("request_ids.amount", "line_ids.amount_total", "amount_existing")
    def _compute_amounts(self):
        for rec in self:
            rec.amount_advance = sum(rec.request_ids.mapped("amount"))
            rec.amount_spent = (
                sum(rec.line_ids.mapped("amount_total")) + rec.amount_existing)
            rec.amount_return = rec.amount_advance - rec.amount_spent

    @api.constrains("existing_bill_ids")
    def _check_existing_bills(self):
        for rec in self:
            bad = rec.existing_bill_ids.filtered(
                lambda m: m.move_type not in ("in_invoice", "in_refund")
                or m.state != "posted" or m.petty_clearing_id)
            if bad:
                raise UserError(
                    "บิลต่อไปนี้ใช้ไม่ได้ (ต้องเป็นบิลซื้อหรือใบลดหนี้ผู้ขายที่ post แล้ว "
                    "และไม่ใช่บิลที่เกิดจากใบเคลียร์): "
                    + ", ".join(bad.mapped("name")))
            rec._check_bills_not_used_elsewhere()

    def _check_bills_not_used_elsewhere(self):
        """บิลใบเดียวห้ามอยู่ในใบเคลียร์มากกว่าหนึ่งใบ — ไม่งั้นทะเบียนกองนับยอดซ้ำ
        (ใบเคลียร์ที่ยกเลิกจะปล่อยบิลคืนอยู่แล้วตอน action_cancel)"""
        self.ensure_one()
        if not self.existing_bill_ids:
            return
        others = self.search([
            ("id", "!=", self._origin.id or 0),
            ("state", "!=", "cancel"),
            ("existing_bill_ids", "in", self.existing_bill_ids.ids),
        ])
        if others:
            clashes = [
                "%s → %s" % (
                    other.name,
                    ", ".join((other.existing_bill_ids & self.existing_bill_ids)
                              .mapped("name")))
                for other in others
            ]
            raise UserError(
                "บิลต่อไปนี้ถูกใช้ในใบเคลียร์อื่นแล้ว ดึงซ้ำไม่ได้ "
                "(ยอดเงินของกองจะถูกนับสองครั้ง): " + " | ".join(clashes))

    def _compute_bill_count(self):
        for rec in self:
            rec.bill_count = len(rec.bill_ids)

    @api.onchange("fund_id")
    def _onchange_fund_id_fill_requests(self):
        """เลือกกองแล้วดึงใบเบิกค้างเคลียร์ของกองมาให้อัตโนมัติ (เอาออกได้)
        — กันเหตุลืมผูกใบเบิกแล้วยอดกองเพี้ยน"""
        if self.state != "draft":
            return
        if not self.fund_id:
            self.request_ids = [(5, 0, 0)]
            return
        open_reqs = self.env["petty.cash.request"].search([
            ("fund_id", "=", self.fund_id._origin.id or self.fund_id.id),
            ("state", "=", "paid"),
            ("clearing_id", "=", False),
        ])
        self.request_ids = [(6, 0, open_reqs.ids)]

    # ------------------------------------------------------------------
    # สร้าง draft vendor bills
    # ------------------------------------------------------------------
    def _check_lines_before_billing(self):
        self.ensure_one()
        if not self.line_ids and not self.existing_bill_ids:
            raise UserError("ยังไม่มีรายการใบเสร็จหรือบิลตั้งหนี้")
        self._check_bills_not_used_elsewhere()
        # ด่านกันลืมผูกใบเบิก: กองมีใบเบิกค้างแต่ใบเคลียร์นี้ไม่ได้ดึงมาเลย
        if not self.request_ids and not self.reimburse_ok:
            open_reqs = self.env["petty.cash.request"].search([
                ("fund_id", "=", self.fund_id.id),
                ("state", "=", "paid"),
                ("clearing_id", "=", False),
            ])
            if open_reqs:
                raise UserError(
                    "กอง %s มีใบเบิกค้างเคลียร์ %d ใบ (รวม %s บาท): %s\n\n"
                    "→ ดึงใบเบิกเข้าแท็บ 'ใบเบิกที่เคลียร์' ก่อน\n"
                    "→ หรือถ้าใบเคลียร์นี้เป็นเงินสำรองจ่าย ไม่เกี่ยวกับใบเบิกพวกนั้น "
                    "ให้ติ๊กช่อง 'ยืนยันกรณีสำรองจ่าย'" % (
                        self.fund_id.code,
                        len(open_reqs),
                        f"{sum(open_reqs.mapped('amount')):,.2f}",
                        ", ".join(open_reqs.mapped("name")),
                    ))
        # ด่านยอดใช้เกินเบิก (เงินทอนติดลบ) — จับทั้งเคสสำรองจ่ายและคีย์ยอดผิด
        if self.amount_return < 0 and not self.reimburse_ok:
            raise UserError(
                "ยอดใช้จ่ายจริง (%s) เกินยอดเบิก (%s) อยู่ %s บาท\n\n"
                "→ ถ้าสาขาสำรองจ่ายจริง ติ๊กช่อง 'ยืนยันกรณีสำรองจ่าย' แล้วกดใหม่\n"
                "→ ถ้าไม่ใช่ ตรวจยอดที่คีย์หรือใบเบิกที่ดึงมาอีกครั้ง" % (
                    f"{self.amount_spent:,.2f}",
                    f"{self.amount_advance:,.2f}",
                    f"{-self.amount_return:,.2f}",
                ))
        bad = self.line_ids.filtered(
            lambda l: l.tax_id and not l.partner_id.vat)
        if bad:
            raise UserError(
                "รายการที่ขอคืน VAT ต้องเป็นร้านค้าจริงที่มีเลขผู้เสียภาษี "
                "(ใช้ partner กลางไม่ได้ เพราะรายงานภาษีซื้อ ภ.พ.30 ต้องการชื่อ+เลขผู้เสียภาษี):\n- "
                + "\n- ".join(bad.mapped(lambda l: f"{l.description} ({l.partner_id.name})"))
            )
        no_ref = self.line_ids.filtered(lambda l: l.tax_id and not l.receipt_ref)
        if no_ref:
            raise UserError(
                "รายการที่ขอคืน VAT ต้องกรอกเลขที่ใบกำกับภาษีในช่อง 'เลขที่ใบเสร็จ/ใบกำกับ' "
                "(ใช้กรอกแท็บ Tax Invoice ของบิลอัตโนมัติ):\n- "
                + "\n- ".join(no_ref.mapped("description"))
            )
        # ด่านอนุมัติข้อมูลหลัก (ทำงานเฉพาะเมื่อติดตั้ง custom_master_data_approval)
        # — ให้ error โผล่ตั้งแต่หน้าใบเคลียร์ ไม่ใช่สร้างบิล draft ค้างแล้วไปตายตอน post
        if "az.approval.type" in self.env:
            self.env["az.approval.type"].check_partners(
                self.line_ids.mapped("partner_id"),
                "สร้างบิลจากใบเคลียร์ %s" % self.name)

    def _bill_group_key(self, line):
        # ใบกำกับภาษี/ใบเสร็จใบเดียวกัน (ร้านเดียวกัน + เลขที่เดียวกัน) รวมเป็น bill เดียว
        # ไม่มีเลขที่ใบเสร็จ → แยก bill รายบรรทัด
        return (line.partner_id.id, line.receipt_ref.strip()) if line.receipt_ref else (
            line.partner_id.id, f"__line_{line.id}")

    def action_create_bills(self):
        for rec in self:
            if rec.state not in ("draft", "billed"):
                raise UserError("สร้างบิลได้เฉพาะสถานะร่าง/สร้างบิลแล้ว")
            rec._check_lines_before_billing()

            pending = rec.line_ids.filtered(lambda l: not l.move_id)
            groups = {}
            for line in pending:
                groups.setdefault(rec._bill_group_key(line), []).append(line)

            for lines in groups.values():
                first = lines[0]
                move = self.env["account.move"].create({
                    "move_type": "in_invoice",
                    "journal_id": rec.fund_id.bill_journal_id.id,
                    "partner_id": first.partner_id.id,
                    "invoice_date": first.receipt_date,
                    "date": rec.date,
                    "ref": first.receipt_ref or f"{rec.name} {first.description}",
                    "petty_clearing_id": rec.id,
                    "invoice_line_ids": [
                        Command.create({
                            "name": line.description,
                            "account_id": line.expense_account_id.id,
                            "quantity": 1.0,
                            "price_unit": line.amount_untaxed,
                            "tax_ids": [Command.set(line.tax_id.ids)],
                            # บรรทัดที่ระบุ "สาขาที่ใช้" ลง analytic สาขานั้นแทน
                            # (เคสไปทำงานต่างสาขา) — ปกติใช้ analytic ของกอง
                            "analytic_distribution": {
                                str((line.analytic_account_id
                                     or rec.fund_id.analytic_account_id).id): 100},
                            "wht_tax_id": line.wht_tax_id.id or False,
                        })
                        for line in lines
                    ],
                })
                for line in lines:
                    line.move_id = move
                # กรอกแท็บ Tax Invoice ให้บิลที่มี VAT (l10n_th_account_tax
                # บังคับก่อน post) — เลข/วันที่มาจากใบกำกับที่คีย์ไว้แล้ว
                if move.tax_invoice_ids:
                    move.tax_invoice_ids.write({
                        "tax_invoice_number": first.receipt_ref,
                        "tax_invoice_date": first.receipt_date,
                    })

            rec.request_ids.filtered(lambda r: r.state == "paid").state = "cleared"
            rec.state = "billed"

    def action_post_and_pay(self):
        """จบในจอเดียว: สร้างบิล (ถ้ายัง) → post ทุกบิล → จ่ายจาก journal สาขา
        (หัก WHT อัตโนมัติตาม wht_tax_id บนบรรทัด) รวมบิลตั้งหนี้ที่ดึงเข้ามาด้วย"""
        for rec in self:
            if rec.state == "draft" or rec.line_ids.filtered(lambda l: not l.move_id):
                rec.action_create_bills()
            draft_bills = rec.bill_ids.filtered(lambda m: m.state == "draft")
            draft_bills.action_post()
            to_pay = (rec.bill_ids | rec.existing_bill_ids).filtered(
                lambda m: m.state == "posted"
                and m.payment_state in ("not_paid", "partial"))
            paid_names = [rec._pay_batch(batch) for batch in rec._pay_batches(to_pay)]
            rec.message_post(body=(
                f"Post + จ่ายทั้งชุดจาก journal {rec.fund_id.journal_id.code}: "
                f"post {len(draft_bills)} บิล, จ่าย {len(paid_names)} รายการ"
                + (" — " + ", ".join(paid_names) if paid_names else "")))

    @staticmethod
    def _pay_batches(to_pay):
        """แบ่งบิลที่จะจ่ายเป็นก้อน ๆ — ผู้ขายรายเดียวกันจ่ายรวมครั้งเดียว
        (บิล + ใบลดหนี้หักกลบกันในตัว) เพื่อให้ได้หนังสือรับรองหัก ณ ที่จ่าย
        ใบเดียวยอดรวม แทนที่จะออกทีละใบตามบิล

        ข้อจำกัดที่ต้องแยกก้อน: l10n_th_account_tax คำนวณ WHT ให้ได้แค่
        อัตราเดียวต่อการจ่าย 1 ครั้ง (_prepare_deduction_list แยก entry ต่ออัตรา
        แล้ว wizard รับแค่ entry เดียว) — ถ้าเอาบิลคนละอัตรามารวมก้อนเดียว
        ระบบจะ **ไม่หักภาษีให้เลยแบบเงียบ ๆ** จึงต้องแยกก้อนตามอัตราเสมอ
        (ถ้าติดตั้ง l10n_th_account_tax_multi เมื่อไหร่ ข้อจำกัดนี้ถึงจะหมดไป)"""
        batches = []
        for partner in to_pay.partner_id:
            moves = to_pay.filtered(lambda m, p=partner: m.partner_id == p)
            groups = {}
            for move in moves:
                # บิลใบเดียวที่มี WHT ปนหลายอัตราอยู่แล้ว แยกก้อนของมันเอง
                # (เคสนี้ระบบคำนวณ WHT ให้ไม่ได้อยู่แล้วตั้งแต่ก่อนรวมจ่าย)
                key = tuple(sorted(move.line_ids.wht_tax_id.ids))
                groups[key] = groups.get(key, move.browse()) | move
            no_wht = groups.pop((), None)
            if no_wht is not None:
                single = [key for key in groups if len(key) == 1]
                # บิลไม่มี WHT ไปรวมกับก้อนที่มีอัตราเดียวได้ ฐานภาษีไม่เปลี่ยน
                # แต่ถ้ามีหลายอัตราให้ยืนเป็นก้อนของตัวเอง จะได้ไม่ต้องเลือกข้าง
                if len(groups) == 1 and single:
                    groups[single[0]] |= no_wht
                else:
                    groups[()] = no_wht
            batches.extend(groups.values())
        return batches

    def _pay_batch(self, batch):
        """จ่ายบิล/ใบลดหนี้หนึ่งก้อน (ผู้ขายรายเดียวกัน) จาก journal ของกอง
        คืนข้อความสรุปสำหรับ log"""
        self.ensure_one()
        names = ", ".join(batch.mapped("name"))
        net = sum(self._bill_sign(move) * move.amount_residual for move in batch)
        if self.currency_id.is_zero(net):
            # ใบลดหนี้เท่ายอดบิลพอดี → ไม่มีเงินสดออกจากกอง จับคู่ปิดกันเองพอ
            # (ถ้าฝืนเปิด wizard จะตายด้วย "nothing left to pay")
            payable = batch.line_ids.filtered(
                lambda l: l.account_type == "liability_payable" and not l.reconciled)
            payable.reconcile()
            return f"{names} (หักกลบกันพอดี ไม่มีเงินสดออกจากกอง)"
        if net < 0:
            raise UserError(
                "ผู้ขาย %s: ใบลดหนี้ที่ดึงมามากกว่ายอดบิลในใบเคลียร์นี้ %s บาท (%s)\n\n"
                "→ ดึงบิลของผู้ขายรายนี้เข้ามาให้ครบก่อน\n"
                "→ หรือเอาใบลดหนี้ส่วนที่เกินออก แล้วให้ฝ่ายบัญชีจัดการเงินที่ผู้ขาย"
                "คืนกลับมาแยกต่างหาก" % (
                    batch[0].partner_id.name, f"{-net:,.2f}", names))
        # เปิด wizard จาก journal items เพื่อให้ l10n_th_account_tax
        # คำนวณหัก ณ ที่จ่ายจาก wht_tax_id บนบรรทัดโดยอัตโนมัติ
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move.line",
            active_ids=batch.line_ids.ids,
        ).create({
            "journal_id": self.fund_id.journal_id.id,
            "payment_date": self.date,
        })
        if len(batch) > 1:
            # บังคับรวมเป็นการจ่ายก้อนเดียว ไม่งั้น Odoo แยกจ่ายรายใบ
            # (จ่ายเต็มยอดบิลใบหนึ่ง + รับเงินคืนอีกใบ) ซึ่งไม่ตรงกับเงินสดที่ออกจริง
            wizard.group_payment = True
        # แตะ amount ก่อนเพื่อ trigger lazy compute ของ l10n_th_account_tax
        # (_compute_amount เป็นคนตั้ง wht_tax_id/wht_amount_base บน wizard —
        # ถ้าไม่แตะ ค่า WHT จะยังว่างตอนเช็คบรรทัดถัดไป)
        wizard.amount  # noqa: B018
        # บังคับ writeoff เข้า บัญชี WHT ค้างจ่าย (ไม่งั้นส่วนต่างค้างเป็น
        # partial และไม่เกิด withholding.move สำหรับออก 50 ทวิ)
        if wizard.wht_tax_id and wizard.payment_difference:
            wizard.payment_difference_handling = "reconcile"
            wizard.writeoff_account_id = wizard.wht_tax_id.account_id
            wizard.writeoff_label = wizard.wht_tax_id.display_name
        wizard.action_create_payments()
        return f"{names} ({net:,.2f})"

    def action_view_bills(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": f"Vendor Bills — {self.name}",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("petty_clearing_id", "=", self.id)],
            "context": {"create": False},
        }

    def action_cancel(self):
        for rec in self:
            if rec.state == "replenished":
                raise UserError("ใบเคลียร์ที่เติมเงินแล้วยกเลิกไม่ได้")
            posted = rec.bill_ids.filtered(lambda m: m.state == "posted")
            if posted:
                raise UserError(
                    "มี vendor bill ที่ post แล้ว: "
                    + ", ".join(posted.mapped("name"))
                    + "\nให้ฝ่ายบัญชี reset บิลเป็น draft ก่อนยกเลิกใบเคลียร์"
                )
            paid_existing = rec.existing_bill_ids.filtered(
                lambda m: m.payment_state not in ("not_paid",))
            if paid_existing:
                raise UserError(
                    "บิลตั้งหนี้ต่อไปนี้ถูกจ่ายไปแล้ว ต้องให้บัญชียกเลิก payment ก่อน: "
                    + ", ".join(paid_existing.mapped("name")))
            rec.bill_ids.filtered(lambda m: m.state == "draft").button_cancel()
            rec.line_ids.move_id = False
            rec.existing_bill_ids = [(5, 0, 0)]
            rec.request_ids.filtered(lambda r: r.state == "cleared").state = "paid"
            rec.request_ids.clearing_id = False
            rec.state = "cancel"

    def action_reset_draft(self):
        for rec in self:
            if rec.state != "cancel":
                raise UserError("Reset ได้เฉพาะใบเคลียร์ที่ยกเลิกแล้ว")
            rec.state = "draft"

    def action_back_to_draft(self):
        """กลับไปแก้ใบเคลียร์ที่สร้างบิลแล้ว โดยไม่ต้องยกเลิกทั้งใบก่อน —
        ทำได้เฉพาะตอนที่ยังไม่มีรายการบัญชีจริงเกิดขึ้น (บิลยัง draft ทุกใบ)
        ไม่งั้นทะเบียนกองกับบัญชีจะไม่ตรงกัน"""
        for rec in self:
            if rec.state != "billed":
                raise UserError(
                    "ปุ่มนี้ใช้กับใบเคลียร์สถานะ 'สร้างบิลแล้ว' เท่านั้น "
                    "(ใบที่ยกเลิกไปแล้วใช้ปุ่ม 'กลับเป็นร่าง' ตามเดิม)")
            if rec.replenish_id:
                raise UserError(
                    "ใบเคลียร์นี้ถูกดึงเข้าใบขอเติมเงิน %s แล้ว — "
                    "ต้องเอาออกจากใบขอเติมเงินก่อน ไม่งั้นยอดขอเติมเงินจะไม่ตรง"
                    % rec.replenish_id.name)
            posted = rec.bill_ids.filtered(lambda m: m.state == "posted")
            if posted:
                raise UserError(
                    "มี vendor bill ที่ post แล้ว: " + ", ".join(posted.mapped("name"))
                    + "\nบิลที่ post แล้วมีรายการบัญชีจริงเกิดขึ้น ถ้าย้อนมาแก้ใบเคลียร์"
                    " ทะเบียนกองจะไม่ตรงกับบัญชี — ให้ฝ่ายบัญชี reset บิลเป็น draft ก่อน")
            paid_existing = rec.existing_bill_ids.filtered(
                lambda m: m.payment_state != "not_paid")
            if paid_existing:
                raise UserError(
                    "บิลตั้งหนี้ต่อไปนี้ถูกจ่ายด้วยเงินสดย่อยไปแล้ว: "
                    + ", ".join(paid_existing.mapped("name"))
                    + "\nต้องให้บัญชียกเลิก payment ก่อนถึงจะย้อนมาแก้ใบเคลียร์ได้")
            # บิล draft ยังไม่มีเลขที่/ไม่มี JE ลบทิ้งได้ ไม่ทิ้งขยะไว้ในระบบ
            # (กด Post + จ่ายทั้งชุด รอบใหม่ ระบบสร้างให้ใหม่จากบรรทัดใบเสร็จ)
            dropped = rec.bill_ids.filtered(lambda m: m.state == "draft")
            count = len(dropped)
            rec.line_ids.move_id = False
            dropped.unlink()
            # ปล่อยใบเบิกกลับเป็น "จ่ายเงินแล้ว" ให้ด่านกันลืมผูกใบเบิกทำงานต่อได้
            rec.request_ids.filtered(lambda r: r.state == "cleared").state = "paid"
            rec.state = "draft"
            rec.message_post(body=(
                "กลับเป็นร่างเพื่อแก้ไข — ลบ vendor bill ที่ยังเป็น draft %d ใบ "
                "(บิลตั้งหนี้ที่ดึงมายังอยู่ในใบเคลียร์ตามเดิม)" % count))

    def unlink(self):
        if any(c.state not in ("draft", "cancel") for c in self):
            raise UserError("ลบได้เฉพาะใบเคลียร์สถานะร่าง/ยกเลิก")
        return super().unlink()


class PettyCashClearingLine(models.Model):
    _name = "petty.cash.clearing.line"
    _description = "รายการใบเสร็จในใบเคลียร์เงินสดย่อย"
    _order = "receipt_date, id"

    clearing_id = fields.Many2one(
        "petty.cash.clearing", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="clearing_id.company_id")
    currency_id = fields.Many2one(related="clearing_id.currency_id")
    receipt_date = fields.Date(string="วันที่ใบเสร็จ", required=True)
    partner_id = fields.Many2one(
        "res.partner", string="ร้านค้า", required=True,
        default=lambda self: self.env.ref(
            "custom_petty_cash.partner_no_receipt", raise_if_not_found=False),
        domain="[('supplier_rank', '>', 0)]")
    receipt_ref = fields.Char(
        string="เลขที่ใบเสร็จ/ใบกำกับ",
        help="ร้านเดียวกัน+เลขที่เดียวกัน จะรวมเป็น vendor bill ใบเดียว")
    description = fields.Char(string="รายการ", required=True)
    # เปิดทุกหมวดที่งานจริงใช้ (บัญชีขอ 27 ส.ค. 69) — ปิดเฉพาะหมวดอันตราย
    # ที่เลือกแล้วรายการบัญชีจะเพี้ยนแน่นอน: ลูกหนี้/เจ้าหนี้ (ระบบคุมผ่าน partner),
    # เงินสด-ธนาคาร (ห้ามเดบิตจากบิลซื้อ), ทุน, บัญชี view ของผังลำดับชั้น
    expense_account_id = fields.Many2one(
        "account.account", string="หมวดค่าใช้จ่าย", required=True,
        domain="[('deprecated', '=', False), ('account_type', 'not in', "
        "('asset_receivable', 'liability_payable', 'asset_cash', "
        "'liability_credit_card', 'equity', 'equity_unaffected', "
        "'off_balance', 'view'))]")
    amount_entry = fields.Monetary(string="จำนวนเงิน", required=True)
    tax_included = fields.Boolean(
        string="ยอดรวม VAT",
        help="ติ๊กเมื่อจำนวนเงินที่กรอกเป็นยอดรวม VAT แล้ว (ระบบถอด VAT ย้อนให้) — "
        "ไม่ติ๊ก = จำนวนเงินเป็นยอดก่อน VAT")
    tax_id = fields.Many2one(
        "account.tax", string="VAT",
        domain="[('type_tax_use', '=', 'purchase')]")
    wht_tax_id = fields.Many2one(
        "account.withholding.tax", string="หัก ณ ที่จ่าย",
        help="เลือกเมื่อเป็นค่าบริการที่ต้องหัก ณ ที่จ่าย — "
        "ระบบจะหักตอนจ่ายบิลและออก 50 ทวิให้อัตโนมัติ")
    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="สาขาที่ใช้",
        help="เว้นว่าง = ค่าใช้จ่ายลง analytic ของกองตามปกติ — "
        "เลือกเฉพาะเมื่อบรรทัดนี้เป็นค่าใช้จ่ายของสาขาอื่น "
        "(เช่น ผู้จัดการเบิกจากกองนี้แต่ไปทำงานอีกสาขา) "
        "เงินยังออกจากกองนี้และเติมคืนกองนี้เต็มยอดเหมือนเดิม")
    amount_wht = fields.Monetary(
        string="ยอดหัก ณ ที่จ่าย", compute="_compute_amount_wht", store=True,
        help="ยอดที่จะถูกหักตอนจ่าย = ยอดก่อน VAT × อัตรา WHT (แสดงเพื่อทราบ — "
        "การหักจริงเกิดตอน register payment)")
    amount_untaxed = fields.Monetary(
        string="ยอดก่อน VAT", compute="_compute_amounts", store=True)
    amount_tax = fields.Monetary(string="ยอด VAT", compute="_compute_amounts", store=True)
    amount_total = fields.Monetary(string="รวม", compute="_compute_amounts", store=True)
    move_id = fields.Many2one(
        "account.move", string="Vendor Bill", readonly=True, copy=False)
    move_state = fields.Selection(related="move_id.state", string="สถานะบิล")
    receipt_image = fields.Image(
        string="รูปใบเสร็จ", max_width=1920, max_height=1920, copy=False,
        help="รูปถ่าย/สแกนใบเสร็จของบรรทัดนี้ (เก็บเป็นไฟล์แนบ ไม่พิมพ์ลงฟอร์ม)")

    @api.depends("amount_untaxed", "wht_tax_id", "wht_tax_id.amount")
    def _compute_amount_wht(self):
        for line in self:
            # WHT แบบ PIT คำนวณตามอัตราก้าวหน้าตอนจ่ายจริง — แสดง 0 ไว้ก่อน
            if line.wht_tax_id and not getattr(line.wht_tax_id, "is_pit", False):
                line.amount_wht = line.currency_id.round(
                    line.amount_untaxed * line.wht_tax_id.amount / 100.0)
            else:
                line.amount_wht = 0.0

    @api.depends("amount_entry", "tax_included", "tax_id")
    def _compute_amounts(self):
        for line in self:
            if not line.tax_id:
                line.amount_untaxed = line.amount_entry
                line.amount_tax = 0.0
                line.amount_total = line.amount_entry
                continue
            if line.tax_included:
                # ถอด VAT ย้อนจากยอดรวมตามบิล (รองรับภาษีแบบเปอร์เซ็นต์)
                if line.tax_id.amount_type == "percent":
                    base = line.currency_id.round(
                        line.amount_entry / (1 + line.tax_id.amount / 100.0))
                else:
                    base = line.amount_entry
                line.amount_untaxed = base
                line.amount_tax = line.amount_entry - base
                line.amount_total = line.amount_entry
            else:
                res = line.tax_id.compute_all(
                    line.amount_entry,
                    currency=line.currency_id,
                    quantity=1.0,
                    partner=line.partner_id,
                )
                line.amount_untaxed = line.amount_entry
                line.amount_total = res["total_included"]
                line.amount_tax = res["total_included"] - res["total_excluded"]
