# -*- coding: utf-8 -*-
"""สาขา (analytic account) บน PO

* หัว PO: az_branch_id — เลือกครั้งเดียว เติม analytic_distribution ให้ทุกบรรทัด (100%)
  บรรทัดใหม่สืบทอด; แก้รายบรรทัดได้ถ้าซื้อให้หลายสาขาในใบเดียว
* บรรทัด PO: az_branch_id (stored, compute จาก analytic_distribution = บัญชีที่มีสัดส่วนมากสุด)
  + inverse: ตั้งค่าจาก list/multi-edit แล้วเขียนกลับเป็น analytic_distribution {id: 100}
* หัว PO: az_branch_ids (stored) = สาขาทั้งหมดที่ปรากฏบนบรรทัด -> คอลัมน์/ตัวกรอง/จัดกลุ่มบน list
* บังคับ: ยืนยัน PO ไม่ได้ถ้ามีบรรทัดสินค้าที่ยังไม่ระบุสาขา
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _main_account_id(distribution):
    """คืน id ของ analytic account ที่มีสัดส่วนสูงสุดใน distribution (key อาจเป็น '12' หรือ '12,34')"""
    best_id, best_pct = False, -1.0
    for key, pct in (distribution or {}).items():
        try:
            pct = float(pct)
        except (TypeError, ValueError):
            pct = 0.0
        for part in str(key).split(","):
            part = part.strip()
            if part.isdigit() and pct > best_pct:
                best_id, best_pct = int(part), pct
    return best_id


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    az_branch_id = fields.Many2one(
        "account.analytic.account", "สาขา",
        domain="[('company_id', 'in', (company_id, False))]",
        help="เลือกแล้วระบบเติมสาขาให้ทุกบรรทัดทันที ถ้าใบเดียวซื้อให้หลายสาขา ให้เลือกหัวใบก่อนแล้วค่อยแก้คอลัมน์สาขารายบรรทัด",
        tracking=True,
    )
    az_branch_ids = fields.Many2many(
        "account.analytic.account", "az_purchase_order_branch_rel", "order_id", "account_id",
        string="สาขา (จากบรรทัด)", compute="_compute_az_branch_ids", store=True,
    )
    az_branch_display = fields.Char("สาขา", compute="_compute_az_branch_ids", store=True)

    @api.depends("order_line.az_branch_id")
    def _compute_az_branch_ids(self):
        for order in self:
            branches = order.order_line.filtered(lambda l: not l.display_type).mapped("az_branch_id")
            order.az_branch_ids = [(6, 0, branches.ids)]
            order.az_branch_display = ", ".join(branches.mapped("name"))

    @api.onchange("az_branch_id")
    def _onchange_az_branch_id(self):
        self._apply_branch_to_lines()

    def _apply_branch_to_lines(self):
        """เติมสาขาหัวใบลงทุกบรรทัดสินค้า (กติกาเดียว จำง่าย: หัวใบทับทุกบรรทัด
        ถ้าใบเดียวซื้อให้หลายสาขา ให้เลือกหัวใบก่อนแล้วค่อยแก้รายบรรทัด)"""
        for order in self:
            if not order.az_branch_id:
                continue
            dist = {str(order.az_branch_id.id): 100.0}
            for line in order.order_line:
                if not line.display_type and line.az_branch_id != order.az_branch_id:
                    line.analytic_distribution = dist

    def write(self, vals):
        res = super().write(vals)
        if vals.get("az_branch_id"):
            self._apply_branch_to_lines()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders.filtered("az_branch_id")._apply_branch_to_lines()
        return orders

    def button_confirm(self):
        for order in self:
            if order.state not in ("draft", "sent"):
                continue
            missing = order.order_line.filtered(
                lambda l: not l.display_type and not l.az_branch_id and not l.is_downpayment
            )
            if missing:
                names = "\n".join("- %s" % (l.product_id.display_name or l.name) for l in missing[:10])
                more = _("\n... และอีก %d บรรทัด") % (len(missing) - 10) if len(missing) > 10 else ""
                raise UserError(
                    _("ยืนยันไม่ได้: ยังไม่ระบุสาขา (Analytic) ในบรรทัดต่อไปนี้\n%s%s\n\n"
                      "เลือกช่อง 'สาขา' ที่หัวใบเพื่อเติมให้ทุกบรรทัด หรือระบุรายบรรทัดในคอลัมน์ 'สาขา'")
                    % (names, more)
                )
        return super().button_confirm()


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    az_branch_id = fields.Many2one(
        "account.analytic.account", "สาขา",
        compute="_compute_az_branch_id", inverse="_inverse_az_branch_id", store=True, index=True,
        domain="[('company_id', 'in', (company_id, False))]",
        help="สาขาที่รับผิดชอบค่าใช้จ่ายบรรทัดนี้ (= Analytic ที่มีสัดส่วนมากสุด)",
    )

    @api.depends("analytic_distribution")
    def _compute_az_branch_id(self):
        Account = self.env["account.analytic.account"]
        for line in self:
            acc_id = _main_account_id(line.analytic_distribution)
            line.az_branch_id = Account.browse(acc_id).exists() if acc_id else False

    def _inverse_az_branch_id(self):
        for line in self:
            if line.az_branch_id:
                current = _main_account_id(line.analytic_distribution)
                if current != line.az_branch_id.id:
                    line.analytic_distribution = {str(line.az_branch_id.id): 100.0}
            elif line.analytic_distribution:
                line.analytic_distribution = False

    @api.depends("product_id", "order_id.partner_id", "order_id.az_branch_id")
    def _compute_analytic_distribution(self):
        super()._compute_analytic_distribution()
        for line in self:
            if line.display_type or line.analytic_distribution:
                continue
            branch = line.order_id.az_branch_id
            if branch:
                line.analytic_distribution = {str(branch.id): 100.0}
