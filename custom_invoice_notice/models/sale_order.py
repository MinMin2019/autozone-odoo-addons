# -*- coding: utf-8 -*-
# ใบแจ้งหนี้จากใบสั่งขาย (แบบ B - บัญชีเคาะ 15 ต.ค. 2026)
#   ส่งงานแล้ว -> พิมพ์ "ใบแจ้งหนี้" จาก SO (ยังไม่ออก IV ยังไม่ลงบัญชี) -> ยอดไปขึ้นรายงานคาดรับเงิน
#   -> ลูกค้าจ่าย -> กด Create Invoice ออก IV ลงวันที่รับเงิน (ชุดใบกำกับ 5 ใบเดิม) -> Register Payment (RV)
#   ยอดบนใบแจ้งหนี้ = ส่วนที่ยังไม่ได้ออก IV (qty_to_invoice ของแต่ละบรรทัด)
#   หัก ณ ที่จ่าย = เฉพาะบรรทัดบริการ x อัตราของลูกค้า (กติกาเดียวกับใบแจ้งหนี้บน IV)
#   ใช้ได้เฉพาะ SO ที่เป็นบริการล้วน: สินค้าต้องออกใบกำกับตอนส่งของ (VAT เกิดตอนส่ง) เลื่อนไม่ได้
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _end_of_month(d):
    return (d.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    az_notice_date = fields.Date(
        string="วันที่ใบแจ้งหนี้", copy=False, tracking=True,
        help="ใส่ให้อัตโนมัติ (= วันนี้) ครั้งแรกที่กดพิมพ์ใบแจ้งหนี้ แก้ได้")
    az_notice_due_date = fields.Date(
        string="วันครบกำหนดชำระ (ใบแจ้งหนี้)", copy=False,
        compute="_compute_az_notice_due_date", store=True, readonly=False,
        help="คิดให้ครั้งแรก = วันที่ใบแจ้งหนี้ + เงื่อนไขชำระเงิน (ของใบ หรือของลูกค้า) แก้ได้ "
             "กรอกเองล่วงหน้าได้ = ถือว่าออกใบแจ้งหนี้แล้ว ยอดไปขึ้นรายงานคาดรับเงินในวันนี้")
    az_notice_hide_wht = fields.Boolean(string="ไม่แสดงหัก ณ ที่จ่ายบนใบแจ้งหนี้", copy=False)
    az_notice_bank_id = fields.Many2one(
        "res.partner.bank", string="บัญชีรับโอน (ใบแจ้งหนี้)", copy=False,
        compute="_compute_az_notice_bank_id", store=True, readonly=False,
        domain=lambda self: [("partner_id", "in", self.env["res.company"].sudo().search([]).partner_id.ids)])
    az_notice_state = fields.Selection(
        [("none", "ยังไม่ออกใบแจ้งหนี้"), ("issued", "ออกใบแจ้งหนี้แล้ว รอรับเงิน"), ("invoiced", "ออกใบกำกับแล้ว")],
        string="สถานะใบแจ้งหนี้", compute="_compute_az_notice_amounts")
    az_notice_amount_untaxed = fields.Monetary(string="ยอดก่อน VAT (ใบแจ้งหนี้)", compute="_compute_az_notice_amounts")
    az_notice_amount_tax = fields.Monetary(string="VAT (ใบแจ้งหนี้)", compute="_compute_az_notice_amounts")
    az_notice_amount_total = fields.Monetary(string="ยอดรวม (ใบแจ้งหนี้)", compute="_compute_az_notice_amounts")
    az_notice_service_base = fields.Monetary(string="ค่าบริการก่อน VAT", compute="_compute_az_notice_amounts")
    az_notice_wht_percent = fields.Float(string="อัตราหัก ณ ที่จ่าย (%)", compute="_compute_az_notice_amounts", digits=(5, 2))
    az_notice_wht_amount = fields.Monetary(string="หัก ณ ที่จ่าย (ใบแจ้งหนี้)", compute="_compute_az_notice_amounts")
    az_notice_net_amount = fields.Monetary(string="ยอดชำระสุทธิ (ใบแจ้งหนี้)", compute="_compute_az_notice_amounts")

    # ---------- บรรทัดที่ยังไม่ออก IV ----------
    def _az_notice_lines(self):
        """บรรทัดสินค้าที่ยังเหลือออกใบกำกับ (qty_to_invoice > 0) + section/note คั่น"""
        self.ensure_one()
        return self.order_line.filtered(
            lambda l: l.display_type in ("line_section", "line_note") or (not l.display_type and l.qty_to_invoice > 0))

    @staticmethod
    def _az_line_is_service(line):
        return not line.product_id or line.product_id.type == "service"

    def _az_line_amounts(self, line):
        """(ก่อน VAT, VAT, รวม) ของบรรทัดตามจำนวนที่ยังไม่ออก IV"""
        qty = line.qty_to_invoice
        price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
        res = line.tax_id.compute_all(price, self.currency_id, qty, product=line.product_id,
                                      partner=self.partner_shipping_id)
        return res["total_excluded"], res["total_included"] - res["total_excluded"], res["total_included"]

    @api.depends("order_line.qty_to_invoice", "order_line.price_unit", "order_line.discount", "order_line.tax_id",
                 "order_line.product_id", "az_notice_hide_wht", "az_notice_date", "state",
                 "partner_id.commercial_partner_id.az_wht_deduct", "partner_id.commercial_partner_id.az_wht_percent")
    def _compute_az_notice_amounts(self):
        for so in self:
            untaxed = tax = total = base = 0.0
            for line in so._az_notice_lines().filtered(lambda l: not l.display_type):
                u, t, tot = so._az_line_amounts(line)
                untaxed += u
                tax += t
                total += tot
                if so._az_line_is_service(line):
                    base += u
            cur = so.currency_id
            untaxed, tax, total, base = (cur.round(v) for v in (untaxed, tax, total, base))
            partner = so.partner_id.commercial_partner_id
            pct = partner.az_wht_percent if partner.az_wht_deduct else 0.0
            wht = cur.round(base * pct / 100.0) if (pct and base and not so.az_notice_hide_wht) else 0.0
            so.az_notice_amount_untaxed = untaxed
            so.az_notice_amount_tax = tax
            so.az_notice_amount_total = total
            so.az_notice_service_base = base
            so.az_notice_wht_percent = pct if wht else 0.0
            so.az_notice_wht_amount = wht
            so.az_notice_net_amount = total - wht
            if not so.az_notice_date and not so.az_notice_due_date:
                so.az_notice_state = "none"
            elif total:
                so.az_notice_state = "issued"
            else:
                so.az_notice_state = "invoiced"

    def az_notice_pct_text(self):
        self.ensure_one()
        return "%g" % (self.az_notice_wht_percent or 0.0)

    # ---------- วันครบกำหนด ----------
    @api.depends("az_notice_date", "payment_term_id", "partner_id")
    def _compute_az_notice_due_date(self):
        """คิดให้เฉพาะตอนยังว่าง: ฝ่ายขายกรอกวันครบกำหนดเองล่วงหน้าได้ (ถือว่าออกใบแจ้งหนี้แล้ว) ระบบไม่ทับ"""
        for so in self:
            d = so.az_notice_date
            if so.az_notice_due_date:
                continue
            if not d:
                so.az_notice_due_date = False
                continue
            due = d
            # ไม่มีเงื่อนไขบนใบ (SO ค้างบน prod 22/23 ใบไม่มี) -> ใช้ของลูกค้า -> ไม่มีเลย = วันเดียวกัน (แก้เองได้)
            term = so.payment_term_id or so.partner_id.with_company(so.company_id).property_payment_term_id
            line = term.line_ids[-1:] if term else False
            if line:
                n = line.nb_days or 0
                if line.delay_type == "days_after":
                    due = d + timedelta(days=n)
                elif line.delay_type == "days_after_end_of_month":
                    due = _end_of_month(d) + timedelta(days=n)
                elif line.delay_type == "days_after_end_of_next_month":
                    due = _end_of_month(_end_of_month(d) + timedelta(days=1)) + timedelta(days=n)
                else:  # days_end_of_month_on_the
                    due = _end_of_month(d + timedelta(days=n))
            so.az_notice_due_date = due

    # ---------- บัญชีธนาคาร ----------
    @api.depends("partner_id", "company_id")
    def _compute_az_notice_bank_id(self):
        for so in self:
            so.az_notice_bank_id = so.partner_id.commercial_partner_id.az_notice_last_bank(so.company_id)

    # ---------- พิมพ์ ----------
    def az_notice_copies(self):
        return self.env["account.move"].az_notice_copies()

    def action_print_invoice_notice(self):
        self.ensure_one()
        if self.state != "sale":
            raise UserError(_("ต้องยืนยันใบสั่งขาย (Confirm) ก่อนพิมพ์ใบแจ้งหนี้"))
        lines = self._az_notice_lines().filtered(lambda l: not l.display_type)
        if not lines:
            raise UserError(_("ใบนี้ออกใบกำกับภาษีครบแล้ว ไม่มีรายการเหลือให้แจ้งหนี้"))
        goods = lines.filtered(lambda l: not self._az_line_is_service(l))
        if goods:
            raise UserError(_(
                "ใบแจ้งหนี้ใช้ได้เฉพาะงานบริการ ใบนี้มีสินค้า (%s)\n"
                "สินค้าต้องออกใบกำกับภาษีตอนส่งของ (กด Create Invoice ได้เลย) "
                "ถ้ามีทั้งของและบริการ ให้แยกใบสั่งขาย",
                ", ".join(goods.mapped("product_id.display_name")[:3])))
        if not self.az_notice_date:
            self.az_notice_date = fields.Date.context_today(self)
        if not self.az_notice_due_date:
            self._compute_az_notice_due_date()
        return self.env.ref("custom_invoice_notice.action_report_invoice_notice_so").report_action(self)

    def az_notice_pages(self, per_first=33, per_cont=33, per_last=17, per_single=17):
        """แบ่งหน้าแบบ fill-front เหมือนชุดใบกำกับ (1 บรรทัด = 1 แถว) คืน [{"lines": [...], "rows": n}]"""
        self.ensure_one()
        lines = list(self._az_notice_lines())
        total = len(lines)
        if total <= per_single:
            chunks = [lines]
        else:
            p1 = min(per_first, total - 1)
            chunks = [lines[:p1]]
            i = p1
            while total - i > per_last:
                take = min(per_cont, (total - i) - 1)
                chunks.append(lines[i:i + take])
                i += take
            chunks.append(lines[i:])
        return [{"lines": c, "rows": len(c)} for c in chunks]
