# -*- coding: utf-8 -*-
import logging
import re

_logger = logging.getLogger(__name__)

# ยาวก่อนสั้น: "นางสาว" ต้องมาก่อน "นาง"
_TITLES = ('ว่าที่ ร.ต.หญิง', 'ว่าที่ร.ต.หญิง', 'ว่าที่ ร.ต.', 'นางสาว', 'น.ส.', 'นาย', 'นาง')


def normalize_name(name):
    name = (name or '').strip()
    for title in _TITLES:
        if name.startswith(title):
            name = name[len(title):]
            break
    return re.sub(r'\s+', '', name).lower()


def post_init_hook(env):
    """ย้ายชื่อที่พิมพ์ไว้ในช่อง Repository ไปเป็น Custodian เฉพาะที่ตรงกับพนักงานคนเดียวแบบเป๊ะ"""
    employees = env['hr.employee'].sudo().with_context(active_test=False).search([])
    index = {}
    for emp in employees:
        index.setdefault(normalize_name(emp.name), []).append(emp)

    assets = env['account.asset'].sudo().with_context(active_test=False).search([
        ('x_asset_repository', '!=', False),
        ('custodian_id', '=', False),
    ])
    matched = 0
    for asset in assets:
        found = index.get(normalize_name(asset.x_asset_repository), [])
        if len(found) == 1:
            asset.custodian_id = found[0]
            matched += 1
    _logger.info('custom_asset_tracking: matched %s / %s assets to employees', matched, len(assets))
