# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, fields, models


class AzAttendanceSyncWizard(models.TransientModel):
    _name = 'az.attendance.sync.wizard'
    _description = 'ดึงเวลาตอกบัตรจากเครื่องสแกน'

    def _default_date_to(self):
        return fields.Date.context_today(self.with_context(tz='Asia/Bangkok'))

    def _default_date_from(self):
        return self._default_date_to() - timedelta(days=7)

    date_from = fields.Date(string='ตั้งแต่วันที่', required=True, default=_default_date_from)
    date_to = fields.Date(string='ถึงวันที่', required=True, default=_default_date_to)

    def action_sync(self):
        """ดึงข้อมูลแล้วเปิดผลการดึงให้ดูทันที"""
        self.ensure_one()
        log = self.env['az.attendance.sync'].run_sync(self.date_from, self.date_to, trigger='manual')
        return {
            'type': 'ir.actions.act_window',
            'name': _('ผลการดึงเวลาตอกบัตร'),
            'res_model': 'az.attendance.sync',
            'res_id': log.id,
            'view_mode': 'form',
            'target': 'current',
        }
