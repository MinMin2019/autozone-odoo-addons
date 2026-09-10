from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # post_init_hook รันเฉพาะตอนติดตั้งใหม่ — ฐานที่ติดตั้งแล้วต้องได้
    # บัญชี 111007 + journal PCB ผ่าน migration ตอนอัพเกรดแทน
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.custom_petty_cash.hooks import _setup_petty_cash_outstanding

    _setup_petty_cash_outstanding(env)
