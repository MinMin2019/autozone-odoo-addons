from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """คำนวณยอดรวมใหม่ทุกใบ ให้หักใบลดหนี้ที่จับคู่ตัดกับบิลแล้ว"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    reports = env['vendor.payment.report'].with_context(active_test=False).search([])
    reports._compute_amounts()
    reports.flush_recordset(['amount_total', 'amount_wht', 'amount_net'])
