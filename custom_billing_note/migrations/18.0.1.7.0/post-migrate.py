# -*- coding: utf-8 -*-
"""18.0.1.7.0: ติ๊ก "เป็นบริษัทประกัน" ตั้งต้นให้ลูกค้าที่ชื่อเข้าข่าย (รันครั้งเดียวตอนอัปเกรด)
ลูกค้าประกันรายใหม่หลังจากนี้ ผู้ใช้ติ๊กเองบนหน้าลูกค้า"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    partners = env['res.partner'].az_mark_insurers()
    _logger.warning('custom_billing_note 1.7.0: marked %s partner(s) as insurer: %s',
                    len(partners), ', '.join('%s' % p.id for p in partners))
