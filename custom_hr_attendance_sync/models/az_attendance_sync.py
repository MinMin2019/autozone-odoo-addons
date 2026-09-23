# -*- coding: utf-8 -*-
"""ดึงเวลาตอกบัตรจากฐาน BpControl (SQL Server) เข้า hr.attendance

ต้นทาง: BpControl.dbo.ScanData = สรุปรายวัน 1 แถว/คน/วัน/สาขา มี 6 ช่องเวลา
        m1,m2 = เข้า-ออกช่วงเช้า | a1,a2 = ช่วงบ่าย | e1,e2 = ช่วงเย็น/โอที
ปลายทาง: hr.attendance 1 แถวต่อ 1 ช่วงที่ครบคู่ (มีทั้งเข้าและออก)

หลักการสำคัญ
- เวลาในฐานต้นทางเป็นเวลาไทย (naive) -> แปลงเป็น UTC ก่อนเขียนลง Odoo เสมอ
- รันซ้ำได้: จับคู่ของเดิมด้วย az_source_key ถ้าเวลาเปลี่ยน = แก้, ถ้าหายจากต้นทาง = ลบ
- ช่วงที่ตอกเข้าแต่ไม่ตอกออก จะไม่สร้างแถวค้างไว้ (จะทำให้ Odoo คิดว่าพนักงานยังไม่เลิกงาน)
  แต่นับจำนวนไว้ในรายงานผลการดึง เพื่อให้เห็นว่าวันนั้นข้อมูลไม่ครบกี่เคส
"""
import logging
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.import_payslip_inputs.tools.bplus_extract import Db, ExtractError

_logger = logging.getLogger(__name__)

TZ = pytz.timezone('Asia/Bangkok')

# ช่วงเวลาใน ScanData: (รหัสช่วง, คอลัมน์เข้า, คอลัมน์ออก)
SLOTS = (('m', 'm1', 'm2'), ('a', 'a1', 'a2'), ('e', 'e1', 'e2'))

SQL_SCANDATA = """
SELECT branchId,
       LTRIM(RTRIM(atzScanId))            AS atzScanId,
       CONVERT(varchar(10), scanDate, 23) AS scanDate,
       CONVERT(varchar(19), m1, 120)      AS m1,
       CONVERT(varchar(19), m2, 120)      AS m2,
       CONVERT(varchar(19), a1, 120)      AS a1,
       CONVERT(varchar(19), a2, 120)      AS a2,
       CONVERT(varchar(19), e1, 120)      AS e1,
       CONVERT(varchar(19), e2, 120)      AS e2
FROM dbo.ScanData
WHERE scanDate BETWEEN '{date_from}' AND '{date_to}'
  AND (m1 IS NOT NULL OR a1 IS NOT NULL OR e1 IS NOT NULL)
ORDER BY scanDate, atzScanId
"""


class AzAttendanceSync(models.Model):
    _name = 'az.attendance.sync'
    _description = 'ประวัติการดึงเวลาตอกบัตรจากเครื่องสแกน'
    _order = 'id desc'

    name = fields.Char(string='รอบการดึง', readonly=True)
    date_from = fields.Date(string='ตั้งแต่วันที่', required=True, readonly=True)
    date_to = fields.Date(string='ถึงวันที่', required=True, readonly=True)
    state = fields.Selection(
        [('done', 'สำเร็จ'), ('error', 'ล้มเหลว')],
        string='สถานะ', readonly=True, default='done')
    trigger = fields.Selection(
        [('cron', 'อัตโนมัติรายวัน'), ('manual', 'สั่งด้วยมือ')],
        string='สั่งโดย', readonly=True, default='manual')
    user_id = fields.Many2one('res.users', string='ผู้สั่ง', readonly=True,
                              default=lambda self: self.env.user)
    source_rows = fields.Integer(string='แถวจากต้นทาง', readonly=True)
    created_count = fields.Integer(string='สร้างใหม่', readonly=True)
    updated_count = fields.Integer(string='แก้เวลา', readonly=True)
    deleted_count = fields.Integer(string='ลบ (หายจากต้นทาง)', readonly=True)
    unchanged_count = fields.Integer(string='เหมือนเดิม', readonly=True)
    employee_count = fields.Integer(string='จำนวนพนักงาน', readonly=True)
    incomplete_count = fields.Integer(string='ตอกเข้าไม่ตอกออก', readonly=True)
    dup_branch_count = fields.Integer(
        string='ซ้ำข้ามสาขา (ตัดทิ้ง)', readonly=True,
        help='คนเดียว วันเดียว มีข้อมูลมากกว่า 1 สาขา — เก็บสาขาที่ดูเป็นการสแกนจริงที่สุดไว้แถวเดียว')
    overlap_count = fields.Integer(
        string='ช่วงเวลาทับกัน (ตัดให้)', readonly=True,
        help='ต้นทางมีช่วงเวลาซ้อนกันเอง เช่น ช่วงบ่ายกินไปถึงเวลาเลิกโอที '
             'ระบบตัดหัวช่วงหลังให้เริ่มตอนช่วงก่อนหน้าจบ เพื่อไม่ให้นับชั่วโมงซ้ำ')
    failed_count = fields.Integer(string='สร้างไม่สำเร็จ', readonly=True)
    unmatched_count = fields.Integer(string='ไม่พบพนักงานใน Odoo', readonly=True)
    unmatched_codes = fields.Text(string='รหัสที่ไม่พบ', readonly=True)
    duration = fields.Float(string='ใช้เวลา (วินาที)', readonly=True)
    message = fields.Text(string='รายละเอียด', readonly=True)

    # ------------------------------------------------------------------
    # การเชื่อมต่อ
    # ------------------------------------------------------------------
    @api.model
    def _get_db_config(self):
        """ค่าเชื่อมต่อ BpControl — ใช้ bpcontrol.* ก่อน ถ้าไม่มีถอยไปใช้ bplus.* (เครื่องเดียวกัน)"""
        get = self.env['ir.config_parameter'].sudo().get_param
        cfg = {
            'server': get('bpcontrol.server') or get('bplus.server'),
            'database': get('bpcontrol.database') or 'BpControl',
            'user': get('bpcontrol.user') or get('bplus.user'),
            'password': get('bpcontrol.password') or get('bplus.password'),
            'driver': get('bpcontrol.driver') or get('bplus.driver'),
        }
        missing = [k for k in ('server', 'user', 'password') if not cfg.get(k)]
        if missing:
            raise UserError(_(
                'ยังไม่ได้ตั้งค่าเชื่อมต่อ SQL Server: ขาด %s\n'
                'ตั้งที่ Settings > Technical > System Parameters '
                '(bpcontrol.server / bpcontrol.user / bpcontrol.password '
                'หรือใช้ค่า bplus.* ร่วมกัน)', ', '.join('bpcontrol.' + m for m in missing)))
        return cfg

    # ------------------------------------------------------------------
    # ตัวช่วย
    # ------------------------------------------------------------------
    @staticmethod
    def _to_utc(value):
        """'2026-09-09 07:25:48' (เวลาไทย) -> datetime naive UTC สำหรับเก็บใน Odoo"""
        if not value:
            return None
        text = str(value).strip()[:19]
        if not text or text.upper() == 'NULL':
            return None
        try:
            naive = datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None
        return TZ.localize(naive).astimezone(pytz.utc).replace(tzinfo=None)

    @classmethod
    def _row_quality(cls, row):
        """คะแนนความน่าเชื่อถือของแถว ScanData — ใช้ตัดสินเมื่อคนเดียววันเดียวมีหลายสาขา

        เกณฑ์: (1) มีเวลาครบกี่ช่อง  (2) กี่ช่องที่ 'ดูเหมือนสแกนจริง'
        เวลาที่คนกรอกเองมักลงตัวเป๊ะ (08:00:00 / 13:00:00) ส่วนเวลาที่สแกนจริง
        มักมีวินาที/นาทีเศษ เช่น 07:57:15 — จึงให้แถวที่มีเวลาเศษชนะ
        """
        filled = real = 0
        for col in ('m1', 'm2', 'a1', 'a2', 'e1', 'e2'):
            dt_value = cls._to_utc(row.get(col))
            if not dt_value:
                continue
            filled += 1
            if dt_value.second or dt_value.minute % 15:
                real += 1
        return (real, filled)

    @classmethod
    def _pick_one_branch_per_day(cls, rows):
        """คืน (แถวที่เลือกแล้ว, จำนวนแถวที่ถูกตัดทิ้ง)

        พนักงานคนเดียว วันเดียวกัน อาจมีแถวมากกว่า 1 สาขา (ย้ายสาขา/หัวหน้า 2 สาขา
        ต่างคนต่างกรอกให้) เวลามักทับกัน ซึ่ง Odoo ไม่ยอมให้บันทึกเวลาซ้อนกัน
        จึงต้องเลือกสาขาเดียวก่อน — เลือกแถวที่ดูเป็นการสแกนจริงมากที่สุด
        """
        best = {}
        for row in rows:
            key = ((row.get('atzScanId') or '').strip(), row.get('scanDate'))
            current = best.get(key)
            if current is None:
                best[key] = row
                continue
            # ตัดสินด้วยคะแนน ถ้าเท่ากันใช้ branchId น้อยสุดเพื่อให้ผลคงที่ทุกรอบ
            new_rank = (cls._row_quality(row), -int(row.get('branchId') or 0))
            cur_rank = (cls._row_quality(current), -int(current.get('branchId') or 0))
            if new_rank > cur_rank:
                best[key] = row
        return list(best.values()), len(rows) - len(best)

    @api.model
    def _employee_map(self):
        """{รหัสพนักงาน: id} — รวมพนักงานที่ archive แล้วด้วย เผื่อดึงย้อนหลังของคนที่ลาออก"""
        employees = self.env['hr.employee'].with_context(active_test=False).search_read(
            [('registration_number', '!=', False)], ['registration_number'])
        return {(e['registration_number'] or '').strip(): e['id'] for e in employees}

    # ------------------------------------------------------------------
    # แกนกลาง
    # ------------------------------------------------------------------
    @api.model
    def run_sync(self, date_from, date_to, trigger='manual'):
        """ดึงช่วงวันที่ที่กำหนดแล้วบันทึกผลเป็น 1 แถวใน az.attendance.sync"""
        if isinstance(date_from, str):
            date_from = fields.Date.to_date(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.to_date(date_to)
        if date_from > date_to:
            raise UserError(_('ช่วงวันที่ไม่ถูกต้อง: "ตั้งแต่" ต้องไม่เกิน "ถึง"'))

        started = datetime.now()
        Attendance = self.env['hr.attendance'].sudo()
        stats = dict(source_rows=0, created=0, updated=0, deleted=0, unchanged=0,
                     incomplete=0, failed=0, dup_branch=0, overlap=0)
        unmatched = set()
        notes = []

        # 1) อ่านจากต้นทาง
        try:
            db = Db(self._get_db_config(), allow_sqlcmd=True)
            rows = db.query(SQL_SCANDATA.format(date_from=date_from, date_to=date_to))
        except ExtractError as err:
            return self._log_run(date_from, date_to, trigger, stats, unmatched,
                                 started, state='error', message=str(err))
        stats['source_rows'] = len(rows)

        # 1.5) คนเดียว วันเดียว แต่มีข้อมูลหลายสาขา -> เลือกสาขาเดียว
        rows, stats['dup_branch'] = self._pick_one_branch_per_day(rows)

        # 2) แปลงเป็น "สิ่งที่ควรมีใน Odoo"
        emp_by_code = self._employee_map()
        wanted = {}
        for row in rows:
            code = (row.get('atzScanId') or '').strip()
            employee_id = emp_by_code.get(code)
            if not employee_id:
                unmatched.add(code)
                continue
            scan_date = fields.Date.to_date(row.get('scanDate'))
            prev_out = None          # เวลาออกของช่วงก่อนหน้าในวันเดียวกัน
            for slot, col_in, col_out in SLOTS:
                check_in = self._to_utc(row.get(col_in))
                check_out = self._to_utc(row.get(col_out))
                if not check_in:
                    continue
                if not check_out or check_out <= check_in:
                    stats['incomplete'] += 1
                    continue
                # ต้นทางบางแถวมีช่วงทับกันเอง (เช่น บ่าย 13:00-21:30 กับ โอที 17:30-21:30
                # = คนตอกออกครั้งเดียวตอนจบโอที แต่ช่องโอทีถูกกรอกเพิ่ม) ถ้าปล่อยไว้
                # ชั่วโมงจะถูกนับซ้ำ และ Odoo ก็ไม่ยอมให้บันทึกเวลาซ้อนกันอยู่แล้ว
                # -> ตัดหัวช่วงหลังให้เริ่มตอนช่วงก่อนหน้าจบ ถ้าไม่เหลือเวลาก็ตัดทิ้งทั้งช่วง
                if prev_out and check_in < prev_out:
                    stats['overlap'] += 1
                    if check_out <= prev_out:
                        continue
                    check_in = prev_out
                prev_out = check_out
                key = '%s|%s|%s|%s' % (row.get('branchId'), code, row.get('scanDate'), slot)
                wanted[key] = {
                    'employee_id': employee_id,
                    'check_in': check_in,
                    'check_out': check_out,
                    'az_source': 'bpcontrol',
                    'az_source_key': key,
                    'az_scan_date': scan_date,
                    'in_mode': 'technical',
                    'out_mode': 'technical',
                }

        # 3) เทียบกับของที่มีอยู่แล้วในช่วงวันเดียวกัน (เฉพาะที่ดึงมาจากเครื่องสแกน)
        existing = Attendance.search([
            ('az_source', '=', 'bpcontrol'),
            ('az_scan_date', '>=', date_from),
            ('az_scan_date', '<=', date_to),
        ])
        by_key = {}
        obsolete = Attendance.browse()
        for att in existing:
            if att.az_source_key in wanted and att.az_source_key not in by_key:
                by_key[att.az_source_key] = att
            else:
                obsolete |= att          # หายจากต้นทาง หรือเป็นแถวซ้ำ

        if obsolete:
            stats['deleted'] = len(obsolete)
            obsolete.unlink()

        to_create = []
        for key, vals in wanted.items():
            att = by_key.get(key)
            if not att:
                to_create.append(vals)
            elif (att.check_in != vals['check_in'] or att.check_out != vals['check_out']
                    or att.employee_id.id != vals['employee_id']):
                att.write({'check_in': vals['check_in'], 'check_out': vals['check_out'],
                           'employee_id': vals['employee_id']})
                stats['updated'] += 1
            else:
                stats['unchanged'] += 1

        # 4) สร้าง — ลองยกชุดก่อน ถ้าติด constraint (เช่น ทับกับแถวที่คีย์เอง) ค่อยไล่ทีละแถว
        if to_create:
            try:
                with self.env.cr.savepoint():
                    Attendance.create(to_create)
                stats['created'] = len(to_create)
            except Exception:
                for vals in to_create:
                    try:
                        with self.env.cr.savepoint():
                            Attendance.create(vals)
                        stats['created'] += 1
                    except Exception as err:
                        stats['failed'] += 1
                        if len(notes) < 20:
                            notes.append('%s: %s' % (vals['az_source_key'], err))

        message = '\n'.join(notes) if notes else False
        return self._log_run(date_from, date_to, trigger, stats, unmatched, started,
                             employee_count=len({v['employee_id'] for v in wanted.values()}),
                             message=message)

    def _log_run(self, date_from, date_to, trigger, stats, unmatched, started,
                 employee_count=0, state='done', message=False):
        codes = sorted(c for c in unmatched if c)
        record = self.create({
            'name': '%s > %s' % (date_from, date_to),
            'date_from': date_from,
            'date_to': date_to,
            'state': state,
            'trigger': trigger,
            'source_rows': stats.get('source_rows', 0),
            'created_count': stats.get('created', 0),
            'updated_count': stats.get('updated', 0),
            'deleted_count': stats.get('deleted', 0),
            'unchanged_count': stats.get('unchanged', 0),
            'incomplete_count': stats.get('incomplete', 0),
            'dup_branch_count': stats.get('dup_branch', 0),
            'overlap_count': stats.get('overlap', 0),
            'failed_count': stats.get('failed', 0),
            'employee_count': employee_count,
            'unmatched_count': len(codes),
            'unmatched_codes': ', '.join(codes) or False,
            'duration': (datetime.now() - started).total_seconds(),
            'message': message,
        })
        _logger.info('ดึงเวลาตอกบัตร %s > %s: สร้าง %s / แก้ %s / ลบ %s / ไม่พบพนักงาน %s',
                     date_from, date_to, record.created_count, record.updated_count,
                     record.deleted_count, record.unmatched_count)
        return record

    # ------------------------------------------------------------------
    # cron
    # ------------------------------------------------------------------
    @api.model
    def cron_sync(self):
        """ดึงย้อนหลัง N วันทุกวัน — ย้อนหลังเพราะหัวหน้าสาขายังแก้เวลาของวันก่อน ๆ ได้"""
        days = int(self.env['ir.config_parameter'].sudo().get_param('bpcontrol.sync_days', 7))
        today = fields.Date.context_today(self.with_context(tz='Asia/Bangkok'))
        self.run_sync(today - timedelta(days=max(days, 1)), today, trigger='cron')
