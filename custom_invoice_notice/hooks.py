# -*- coding: utf-8 -*-
# ตอนติดตั้งครั้งแรก:
#   1) ลูกค้านิติบุคคลทุกราย -> ติ๊ก "หักภาษี ณ ที่จ่าย"
#   2) บัญชีหลักของบริษัท = SCB ออมทรัพย์ บางปลาสร้อย 582-2-18275-3 (RVB2 รับเงินลูกค้ามากสุด)
#      + ใส่ชื่อสาขา "บางปลาสร้อย"  (ถ้าไม่พบเลขบัญชีนี้ ปล่อยว่างให้ตั้งเองในหน้าบริษัท)
#   3) เติมบัญชีรับโอนให้ใบขายที่ยังค้างชำระ
import logging

_logger = logging.getLogger(__name__)
DEFAULT_ACC = "582-2-18275-3"
DEFAULT_BRANCH = "บางปลาสร้อย"


def post_init_hook(env):
    Partner = env["res.partner"]
    companies = Partner.with_context(active_test=False).search([("is_company", "=", True)])
    companies.write({"az_wht_deduct": True})
    _logger.info("custom_invoice_notice: WHT flag set on %s company partners", len(companies))

    for company in env["res.company"].search([]):
        bank = env["res.partner.bank"].search([
            ("partner_id", "=", company.partner_id.id),
            ("acc_number", "=", DEFAULT_ACC)], limit=1)
        if bank:
            if not bank.az_branch_name:
                bank.az_branch_name = DEFAULT_BRANCH
            if not company.az_notice_default_bank_id:
                company.az_notice_default_bank_id = bank
            _logger.info("custom_invoice_notice: default bank for %s = %s", company.name, bank.acc_number)
        else:
            _logger.warning("custom_invoice_notice: bank %s not found for %s - set it on the company form",
                            DEFAULT_ACC, company.name)

    moves = env["account.move"].search([
        ("move_type", "=", "out_invoice"), ("state", "=", "posted"),
        ("payment_state", "in", ("not_paid", "partial"))])
    moves._compute_az_notice_bank_id()
    _logger.info("custom_invoice_notice: bank filled on %s open invoices", len(moves))
