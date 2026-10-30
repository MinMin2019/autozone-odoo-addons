# -*- coding: utf-8 -*-
"""ตัวดึงข้อมูลการลงเวลาช่างจาก iGarage

มี 2 งาน แยกกันอิสระ:

1) ดึงจากฐาน MySQL ของ iGarage (cron ทุก 15 นาที)
   - รอบปกติดึงเฉพาะชิ้นงานที่มีการเคลื่อนไหวใน N วันล่าสุด (igarage.recent_days ค่าเริ่มต้น 2)
     แต่เอาประวัติของชิ้นนั้นทั้งหมด จึงได้เวลากดเริ่ม/กดจบครบแม้กดเริ่มไว้หลายวันก่อน
   - _sync_db(full=True) ดึงใหม่ทั้งหมดตั้งแต่ igarage.since_date (ใช้ตอนติดตั้ง ผ่าน odoo shell)

2) ดึง log เว็บเซิร์ฟเวอร์ผ่าน FTPS (cron ทุกชั่วโมง)
   - server รวบ log ของแต่ละวันเป็นไฟล์ /logs/<Mon-YYYY>.tar.gz* ตอน 00:10 แล้วเก็บไว้ ~27 วัน
   - แอปส่ง api_key มาใน URL -> map เป็นโปรไฟล์ผู้บันทึก -> เก็บ "วินาทีที่แอปสั่งลงเวลา"
   - ประมวลผลเฉพาะไฟล์ที่ยังไม่เคยทำ (จำด้วยเวลาแก้ไข + ขนาด เพราะชื่อไฟล์เลื่อนทุกวัน)

การแยกช่องทาง: ชิ้นงานถือว่ามาจากแอป ถ้ามี "วินาทีที่แอปสั่ง" ของผู้บันทึกคนเดียวกัน
ห่างจากเวลากดเริ่มไม่เกิน igarage.match_window วินาที (ค่าเริ่มต้น 4)
วันที่ยังไม่มี log (วันนี้ / ก่อนเริ่มเก็บ log) = 'pending' ไม่นับเป็น PC

เวลาในฐาน iGarage และใน log เป็นเวลาไทย -> แปลงเป็น UTC ก่อนเก็บลง Odoo
"""
import logging
import os
import re
import ssl
import tarfile
import tempfile
import time
from datetime import date, datetime, timedelta
from ftplib import FTP_TLS

from psycopg2.extras import execute_values

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..lib import pymysql

_logger = logging.getLogger(__name__)

TH_OFFSET = timedelta(hours=7)          # Asia/Bangkok ไม่มี DST
P = 'igarage.'
DEFAULTS = {
    'db_port': '3306',
    'since_date': '2026-10-01',
    'exclude_branch_ids': '32,33',      # AMU, AKT = ไม่ใช่งานอู่
    'ontime_seconds': '60',
    'match_window': '4',
    'recent_days': '2',
    'log_files_per_run': '4',
}
WRITE_EP = ('/open', '/close', '/wash', '/qc', '/pause', '/resume')
LOG_TS = re.compile(rb'\[(\d\d)/(\w\w\w)/(\d{4}):(\d\d):(\d\d):(\d\d) ([+-])(\d\d)(\d\d)\] "\S+ ([^" ]*)')
KEYPAT = re.compile(r'[?&]key=([A-Za-z0-9]+)')
MONTHS = {b'Jan': 1, b'Feb': 2, b'Mar': 3, b'Apr': 4, b'May': 5, b'Jun': 6,
          b'Jul': 7, b'Aug': 8, b'Sep': 9, b'Oct': 10, b'Nov': 11, b'Dec': 12}
DUMMY_WORDS = ('dummy', 'สำรอง', 'ผู้ช่วย', 'บาร์โค้ด')

ITEM_COLS = ['ext_item_id', 'ext_job_id', 'job_ref', 'branch_code', 'branch_name', 'date',
             'started', 'finished', 'recorder_ext_id', 'recorder_name', 'worker_ext_id',
             'worker_name', 'worker_code', 'is_dummy', 'channel', 'measurable', 'item_count',
             'app_score', 'ontime_score']

SQL_ITEMS = """
    SELECT job_item_id, branch_id, MIN(job_order_id) AS job_order,
      MIN(CASE WHEN job_item_status_id=2 THEN created_at END) AS started,
      MIN(CASE WHEN job_item_status_id=5 THEN created_at END) AS finished,
      CAST(SUBSTRING_INDEX(GROUP_CONCAT(CASE WHEN job_item_status_id=2
            THEN supervisor_profile_id END ORDER BY created_at), ',', 1) AS UNSIGNED) AS recorder,
      CAST(SUBSTRING_INDEX(GROUP_CONCAT(CASE WHEN job_item_status_id=2
            THEN worker_id END ORDER BY created_at), ',', 1) AS UNSIGNED) AS worker
    FROM job_item_logs
    WHERE {where}
    GROUP BY job_item_id, branch_id
    HAVING started IS NOT NULL AND started >= %s
"""


def _chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


class IgarageUsageSync(models.AbstractModel):
    _name = 'igarage.usage.sync'
    _description = 'iGarage: ตัวดึงข้อมูลการลงเวลา'

    # ------------------------------------------------------------------
    # ค่าตั้ง
    # ------------------------------------------------------------------
    @api.model
    def _param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(P + key) or DEFAULTS.get(key)

    @api.model
    def _set_param(self, key, value):
        self.env['ir.config_parameter'].sudo().set_param(P + key, value)

    @api.model
    def _db_ready(self):
        return all(self._param(k) for k in ('db_host', 'db_name', 'db_user', 'db_password'))

    @api.model
    def _ftp_ready(self):
        return all(self._param(k) for k in ('ftp_host', 'ftp_user', 'ftp_password'))

    @api.model
    def _excluded(self):
        return {int(x) for x in (self._param('exclude_branch_ids') or '').split(',') if x.strip().isdigit()}

    @api.model
    def _mysql(self):
        return pymysql.connect(
            host=self._param('db_host'), port=int(self._param('db_port')),
            user=self._param('db_user'), password=self._param('db_password'),
            database=self._param('db_name'), charset='utf8',
            connect_timeout=25, read_timeout=900)

    @api.model
    def _log_window(self):
        """วันที่ log ครอบคลุมครบ: (ตั้งแต่, ถึง) เป็น date หรือ None"""
        f, u = self._param('log_covered_from'), self._param('log_complete_until')
        return (fields.Date.to_date(f) if f else None, fields.Date.to_date(u) if u else None)

    # ------------------------------------------------------------------
    # ตัวครอบ: จับเวลา บันทึกประวัติ จัดการ error
    # ------------------------------------------------------------------
    @api.model
    def _run(self, kind, trigger, fn):
        Log = self.env['igarage.usage.sync.log'].sudo()
        ready = self._ftp_ready() if kind == 'log' else self._db_ready()
        if not ready:
            if trigger == 'manual':
                Log.create({'name': fields.Datetime.now(), 'kind': kind, 'trigger': trigger,
                            'state': 'skip', 'message': 'ยังไม่ได้ตั้งค่าเชื่อมต่อใน System Parameters (igarage.*)'})
                return None
            return None                       # cron: เงียบไว้ ไม่สร้างประวัติรก
        t0 = time.time()
        try:
            rows, msg = fn()
            Log.create({'name': fields.Datetime.now(), 'kind': kind, 'trigger': trigger, 'state': 'done',
                        'rows': rows, 'message': msg, 'duration': time.time() - t0})
            return rows
        except Exception as e:  # noqa: BLE001 — บันทึกทุก error ไว้ให้เห็นในประวัติ
            _logger.exception('iGarage sync %s failed', kind)
            self.env.cr.rollback()
            Log.create({'name': fields.Datetime.now(), 'kind': kind, 'trigger': trigger, 'state': 'error',
                        'message': '%s: %s' % (type(e).__name__, e), 'duration': time.time() - t0})
            self.env.cr.commit()
            if trigger == 'manual':
                raise UserError(_('ดึงข้อมูลไม่สำเร็จ: %s', e)) from e
            return None

    @api.model
    def cron_sync_db(self):
        return self._run('db', 'cron', lambda: self._sync_db(full=False))

    @api.model
    def cron_sync_logs(self):
        return self._run('log', 'cron', lambda: self._sync_logs(int(self._param('log_files_per_run'))))

    @api.model
    def action_sync_now(self):
        n_log = self._run('log', 'manual', lambda: self._sync_logs(int(self._param('log_files_per_run'))))
        n_db = self._run('db', 'manual', lambda: self._sync_db(full=False))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'ดึงข้อมูล iGarage เสร็จแล้ว',
                'message': 'log เว็บ %s ไฟล์ · ชิ้นงาน %s รายการ — ดูรายละเอียดที่ "ประวัติการดึงข้อมูล"'
                           % (n_log or 0, n_db or 0),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def action_full_resync(self):
        """ดึงใหม่ทั้งหมด (หนัก) — ใช้ผ่าน odoo shell ตอนติดตั้ง ไม่ผูกปุ่มใน UI เพราะเกินเวลา request"""
        self._run('log', 'manual', lambda: self._sync_logs(None))
        return self._run('db_full', 'manual', lambda: self._sync_db(full=True))

    # ------------------------------------------------------------------
    # 1) ฐานข้อมูล iGarage
    # ------------------------------------------------------------------
    @api.model
    def _reference(self, cur):
        cur.execute("SELECT id, abbreviation, branch_name, name FROM branches")
        branches = {}
        for bid, ab, bn, nm in cur.fetchall():
            code = (ab or str(bid)).strip()
            name = (bn or nm or '').strip()
            branches[bid] = (code, name if name and name != '-' else code)
        cur.execute("SELECT upro_id, upro_first_name, upro_last_name FROM user_profiles")
        profiles = {pid: ('%s %s' % (fn or '', ln or '')).strip() or 'profile %s' % pid
                    for pid, fn, ln in cur.fetchall()}
        cur.execute("SELECT id, first_name, last_name, worker_number FROM workers")
        workers = {}
        for wid, fn, ln, num in cur.fetchall():
            name = ('%s %s' % (fn or '', ln or '')).strip() or 'worker %s' % wid
            code = (num or '').strip()
            low = (name + ' ' + code).lower()
            workers[wid] = (name, code, any(w in low for w in DUMMY_WORDS))
        return branches, profiles, workers

    @api.model
    def _sync_db(self, full=False):
        since = self._param('since_date')
        excluded = self._excluded()
        conn = self._mysql()
        try:
            cur = conn.cursor()
            branches, profiles, workers = self._reference(cur)
            raw = []
            if full:
                cur.execute(SQL_ITEMS.format(where='created_at >= %s'), (since, since))
                raw = list(cur.fetchall())
            else:
                now_th = datetime.utcnow() + TH_OFFSET
                recent_from = now_th - timedelta(days=int(self._param('recent_days')))
                cur.execute("SELECT DISTINCT job_item_id FROM job_item_logs WHERE created_at >= %s",
                            (recent_from.strftime('%Y-%m-%d %H:%M:%S'),))
                ids = [r[0] for r in cur.fetchall()]
                for chunk in _chunks(ids, 500):
                    ph = ','.join(['%s'] * len(chunk))
                    cur.execute(SQL_ITEMS.format(where='job_item_id IN (%s)' % ph), tuple(chunk) + (since,))
                    raw.extend(cur.fetchall())
            raw = [r for r in raw if r[1] not in excluded]
            job_ids = {r[2] for r in raw if r[2]}
            refs = {}
            for chunk in _chunks(job_ids, 500):
                ph = ','.join(['%s'] * len(chunk))
                cur.execute("SELECT id, reference FROM job_orders WHERE id IN (%s)" % ph, tuple(chunk))
                refs.update({jid: ref for jid, ref in cur.fetchall()})
        finally:
            conn.close()

        if not raw:
            return 0, 'ไม่มีชิ้นงานที่เปลี่ยนแปลง'
        rows = self._build_item_rows(raw, branches, profiles, workers, refs)
        self._upsert_items(rows)
        self._rebuild_jobs({r[1] for r in rows if r[1]})
        n_pending = sum(1 for r in rows if r[14] == 'pending')
        return len(rows), 'ชิ้นงาน %s รายการ จาก %s จ๊อบ (รอ log %s ชิ้น)%s' % (
            len(rows), len(job_ids), n_pending, ' — ดึงใหม่ทั้งหมดตั้งแต่ %s' % since if full else '')

    @api.model
    def _build_item_rows(self, raw, branches, profiles, workers, refs):
        sec = int(self._param('ontime_seconds'))
        win = int(self._param('match_window'))
        cfrom, cuntil = self._log_window()
        starts = [r[3] - TH_OFFSET for r in raw]
        marks = self._load_marks({r[5] for r in raw if r[5]}, min(starts), max(starts), win)
        out = []
        for (item_id, bid, job_id, started, finished, recorder, worker) in raw:
            st_utc = started - TH_OFFSET
            fi_utc = (finished - TH_OFFSET) if finished else None
            day = started.date()
            channel = self._classify(recorder, st_utc, day, marks, win, cfrom, cuntil)
            measurable = bool(finished and finished >= started)
            ontime = (100.0 if (finished - started).total_seconds() > sec else 0.0) if measurable else None
            app = {'app': 100.0, 'pc': 0.0}.get(channel)
            bcode, bname = branches.get(bid, (str(bid), str(bid)))
            wname, wcode, dummy = workers.get(worker, (None, None, False)) if worker else (None, None, False)
            out.append((
                item_id, job_id, refs.get(job_id), bcode, bname, day,
                st_utc, fi_utc if measurable else None, recorder or None,
                profiles.get(recorder) if recorder else None, worker or None,
                wname, wcode, dummy, channel, measurable, 1, app, ontime,
            ))
        return out

    @api.model
    def _load_marks(self, recorders, lo, hi, win):
        if not recorders:
            return set()
        self.env.cr.execute("""
            SELECT recorder_ext_id, ts FROM igarage_usage_appmark
             WHERE recorder_ext_id = ANY(%s) AND ts BETWEEN %s AND %s
        """, (list(recorders), lo - timedelta(seconds=win), hi + timedelta(seconds=win)))
        return set(self.env.cr.fetchall())

    @staticmethod
    def _classify(recorder, st_utc, day, marks, win, cfrom, cuntil):
        if not cfrom or not cuntil or day < cfrom or day > cuntil:
            return 'pending'
        if recorder:
            for off in range(-win, win + 1):
                if (recorder, st_utc + timedelta(seconds=off)) in marks:
                    return 'app'
        return 'pc'

    @api.model
    def _upsert_items(self, rows):
        cols = ', '.join(ITEM_COLS)
        upd = ', '.join('%s = EXCLUDED.%s' % (c, c) for c in ITEM_COLS[1:])
        uid = self.env.uid
        now = fields.Datetime.now()
        data = [r + (uid, uid, now, now) for r in rows]
        execute_values(self.env.cr._obj, """
            INSERT INTO igarage_usage_item (%s, create_uid, write_uid, create_date, write_date)
            VALUES %%s
            ON CONFLICT (ext_item_id) DO UPDATE SET %s, write_uid = EXCLUDED.write_uid,
                                                     write_date = EXCLUDED.write_date
        """ % (cols, upd), data, page_size=1000)
        self.env['igarage.usage.item'].invalidate_model()

    @api.model
    def _rebuild_jobs(self, job_ids):
        """คำนวณตารางจ๊อบ และจ๊อบ x ช่าง ใหม่จากชิ้นงาน เฉพาะจ๊อบที่ได้รับผลกระทบ"""
        if not job_ids:
            return
        sec = int(self._param('ontime_seconds'))
        uid = self.env.uid
        cr = self.env.cr
        for chunk in _chunks(job_ids, 2000):
            params = {'jobs': list(chunk), 'sec': sec, 'uid': uid}
            cr.execute("""
                INSERT INTO igarage_usage_job (
                    ext_job_id, job_ref, branch_code, branch_name, date, item_count, app_item_count,
                    job_count, channel, measurable, app_score, ontime_score,
                    create_uid, write_uid, create_date, write_date)
                SELECT i.ext_job_id, MAX(i.job_ref), MAX(i.branch_code), MAX(i.branch_name), MIN(i.date),
                       COUNT(*), COUNT(*) FILTER (WHERE i.channel = 'app'), 1,
                       CASE WHEN COUNT(*) FILTER (WHERE i.channel = 'app') = 0
                                 AND COUNT(*) FILTER (WHERE i.channel = 'pending') > 0 THEN 'pending'
                            WHEN COUNT(*) FILTER (WHERE i.channel <> 'app') = 0 THEN 'app'
                            WHEN COUNT(*) FILTER (WHERE i.channel = 'app') = 0 THEN 'pc'
                            ELSE 'mixed' END,
                       BOOL_OR(i.measurable),
                       CASE WHEN COUNT(*) FILTER (WHERE i.channel = 'app') > 0 THEN 100.0
                            WHEN COUNT(*) FILTER (WHERE i.channel = 'pending') > 0 THEN NULL
                            ELSE 0.0 END,
                       CASE WHEN BOOL_OR(i.measurable) THEN
                            CASE WHEN EXTRACT(EPOCH FROM MAX(i.finished) FILTER (WHERE i.measurable)
                                                    - MIN(i.started) FILTER (WHERE i.measurable)) > %(sec)s
                                 THEN 100.0 ELSE 0.0 END END,
                       %(uid)s, %(uid)s, now() at time zone 'utc', now() at time zone 'utc'
                  FROM igarage_usage_item i
                 WHERE i.ext_job_id = ANY(%(jobs)s)
                 GROUP BY i.ext_job_id
                ON CONFLICT (ext_job_id) DO UPDATE SET
                    job_ref = EXCLUDED.job_ref, branch_code = EXCLUDED.branch_code,
                    branch_name = EXCLUDED.branch_name, date = EXCLUDED.date,
                    item_count = EXCLUDED.item_count, app_item_count = EXCLUDED.app_item_count,
                    channel = EXCLUDED.channel, measurable = EXCLUDED.measurable,
                    app_score = EXCLUDED.app_score, ontime_score = EXCLUDED.ontime_score,
                    write_uid = EXCLUDED.write_uid, write_date = EXCLUDED.write_date
            """, params)
            cr.execute("""
                INSERT INTO igarage_usage_job_worker (
                    ext_job_id, worker_ext_id, job_ref, branch_code, branch_name, date, worker_name,
                    worker_code, is_dummy, item_count, job_count, app_score, ontime_score,
                    create_uid, write_uid, create_date, write_date)
                SELECT i.ext_job_id, i.worker_ext_id, MAX(i.job_ref), MAX(i.branch_code), MAX(i.branch_name),
                       MIN(i.date), MAX(i.worker_name), MAX(i.worker_code), BOOL_OR(i.is_dummy), COUNT(*), 1,
                       CASE WHEN COUNT(*) FILTER (WHERE i.channel = 'app') > 0 THEN 100.0
                            WHEN COUNT(*) FILTER (WHERE i.channel = 'pending') > 0 THEN NULL
                            ELSE 0.0 END,
                       CASE WHEN BOOL_OR(i.measurable) THEN
                            CASE WHEN EXTRACT(EPOCH FROM MAX(i.finished) FILTER (WHERE i.measurable)
                                                    - MIN(i.started) FILTER (WHERE i.measurable)) > %(sec)s
                                 THEN 100.0 ELSE 0.0 END END,
                       %(uid)s, %(uid)s, now() at time zone 'utc', now() at time zone 'utc'
                  FROM igarage_usage_item i
                 WHERE i.ext_job_id = ANY(%(jobs)s) AND i.worker_ext_id IS NOT NULL
                 GROUP BY i.ext_job_id, i.worker_ext_id
                ON CONFLICT (ext_job_id, worker_ext_id) DO UPDATE SET
                    job_ref = EXCLUDED.job_ref, branch_code = EXCLUDED.branch_code,
                    branch_name = EXCLUDED.branch_name, date = EXCLUDED.date,
                    worker_name = EXCLUDED.worker_name, worker_code = EXCLUDED.worker_code,
                    is_dummy = EXCLUDED.is_dummy, item_count = EXCLUDED.item_count,
                    app_score = EXCLUDED.app_score, ontime_score = EXCLUDED.ontime_score,
                    write_uid = EXCLUDED.write_uid, write_date = EXCLUDED.write_date
            """, params)
        self.env['igarage.usage.job'].invalidate_model()
        self.env['igarage.usage.job.worker'].invalidate_model()

    # ------------------------------------------------------------------
    # 2) log เว็บเซิร์ฟเวอร์
    # ------------------------------------------------------------------
    @api.model
    def _key_to_profile(self):
        conn = self._mysql()
        try:
            cur = conn.cursor()
            cur.execute("""SELECT u.api_key, p.upro_id FROM users u
                           JOIN user_profiles p ON p.upro_uacc_fk = u.id
                           WHERE u.api_key IS NOT NULL AND u.api_key <> ''""")
            # ฐาน iGarage เทียบข้อความแบบไม่สนตัวพิมพ์เล็กใหญ่ แอปที่พิมพ์คีย์ตัวเล็ก/ใหญ่ต่างกันก็ใช้ได้
            return {k.lower(): pid for k, pid in cur.fetchall()}
        finally:
            conn.close()

    @api.model
    def _ftp(self):
        ftp = FTP_TLS(context=ssl.create_default_context())
        ftp.connect(self._param('ftp_host'), 21, timeout=60)
        ftp.login(self._param('ftp_user'), self._param('ftp_password'))
        ftp.prot_p()
        return ftp

    @api.model
    def _sync_logs(self, max_files=None):
        LogFile = self.env['igarage.usage.logfile'].sudo()
        key2prof = self._key_to_profile() if self._db_ready() else {}
        ftp = self._ftp()
        done_files = 0
        try:
            entries = [(name, facts) for name, facts in ftp.mlsd('/logs')
                       if facts.get('type') == 'file' and '.tar.gz' in name]
            done = {(r.modify, r.size) for r in LogFile.search([])}
            todo = sorted((e for e in entries if (e[1].get('modify'), int(e[1].get('size', 0))) not in done),
                          key=lambda e: e[1].get('modify'))
            n_new = len(todo)
            if max_files:
                todo = todo[:max_files]
            for name, facts in todo:
                stat = self._process_log_file(ftp, name, key2prof)
                LogFile.create(dict(stat, name=name, modify=facts.get('modify'), size=int(facts.get('size', 0))))
                done_files += 1
                self.env.cr.commit()              # ทีละไฟล์ — ถ้ารอบนี้ล้มกลางทาง ไฟล์ที่ทำแล้วไม่ต้องทำซ้ำ
        finally:
            try:
                ftp.quit()
            except Exception:  # noqa: BLE001
                ftp.close()

        n_fixed = self._refresh_window_and_reclassify()
        cfrom, cuntil = self._log_window()
        return done_files, 'ประมวลผล log %s ไฟล์ (ค้างอีก %s) · log ครอบคลุม %s ถึง %s · จัดช่องทางใหม่ %s ชิ้น' % (
            done_files, n_new - done_files, cfrom or '-', cuntil or '-', n_fixed)

    @api.model
    def _process_log_file(self, ftp, name, key2prof):
        fd, path = tempfile.mkstemp(suffix='.tar.gz', prefix='igarage_log_')
        os.close(fd)
        first = last = None
        calls = writes = unknown = 0
        marks = set()
        try:
            with open(path, 'wb') as fh:
                ftp.retrbinary('RETR /logs/%s' % name, fh.write)
            with tarfile.open(path, 'r:gz') as tar:
                for member in tar.getmembers():
                    if not member.isfile() or '.error.' in member.name:
                        continue
                    for raw in tar.extractfile(member):
                        m = LOG_TS.search(raw)
                        if not m:
                            continue
                        dd, mon, yy, hh, mi, ss, sign, oh, om, url = m.groups()
                        local = datetime(int(yy), MONTHS.get(mon, 1), int(dd), int(hh), int(mi), int(ss))
                        if first is None or local < first:
                            first = local
                        if last is None or local > last:
                            last = local
                        if b'/apis/steps' not in url:
                            continue
                        calls += 1
                        text = url.decode('latin1')
                        if not text.split('?')[0].endswith(WRITE_EP):
                            continue
                        km = KEYPAT.search(text)
                        prof = key2prof.get(km.group(1).lower()) if km else None
                        if not prof:
                            unknown += 1
                            continue
                        offset = timedelta(hours=int(oh), minutes=int(om)) * (1 if sign == b'+' else -1)
                        marks.add((prof, local - offset))
                        writes += 1
        finally:
            if os.path.exists(path):
                os.remove(path)
        if marks:
            uid = self.env.uid
            now = fields.Datetime.now()
            execute_values(self.env.cr._obj, """
                INSERT INTO igarage_usage_appmark (recorder_ext_id, ts, create_uid, write_uid, create_date, write_date)
                VALUES %s ON CONFLICT (recorder_ext_id, ts) DO NOTHING
            """, [(p, t, uid, uid, now, now) for p, t in marks], page_size=2000)
        return {
            'first_ts': first - TH_OFFSET if first else False,
            'last_ts': last - TH_OFFSET if last else False,
            'api_calls': calls, 'app_writes': writes, 'unknown_keys': unknown,
        }

    @api.model
    def _refresh_window_and_reclassify(self):
        """อัปเดตช่วงวันที่ log ครอบคลุมครบ แล้วจัดช่องทางให้ชิ้นงานที่เคยรอ log"""
        cr = self.env.cr
        cr.execute("SELECT MIN(first_ts), MAX(last_ts) FROM igarage_usage_logfile")
        first, last = cr.fetchone()
        if not first or not last:
            return 0
        first_th, last_th = first + TH_OFFSET, last + TH_OFFSET
        # ไฟล์แรกเริ่มราว 00:10 ของวันก่อนหน้า -> วันแรกที่ครบคือวันถัดไป
        cfrom = first_th.date() if first_th.time() <= datetime.min.time().replace(minute=1) \
            else first_th.date() + timedelta(days=1)
        # ไฟล์ล่าสุดจบราว 00:10 ของวัน D -> วันที่ครบล่าสุดคือ D-1
        cuntil = last_th.date() - timedelta(days=1)
        self._set_param('log_covered_from', fields.Date.to_string(cfrom))
        self._set_param('log_complete_until', fields.Date.to_string(cuntil))

        Item = self.env['igarage.usage.item'].sudo()
        pend = Item.search([('channel', '=', 'pending'), ('date', '>=', cfrom), ('date', '<=', cuntil)])
        if not pend:
            return 0
        win = int(self._param('match_window'))
        cr.execute("""SELECT id, recorder_ext_id, started, date FROM igarage_usage_item
                       WHERE id = ANY(%s)""", (pend.ids,))
        rows = cr.fetchall()
        marks = self._load_marks({r[1] for r in rows if r[1]}, min(r[2] for r in rows),
                                 max(r[2] for r in rows), win)
        app_ids, pc_ids = [], []
        for rid, rec, st, day in rows:
            ch = self._classify(rec, st, day, marks, win, cfrom, cuntil)
            (app_ids if ch == 'app' else pc_ids).append(rid)
        if app_ids:
            cr.execute("UPDATE igarage_usage_item SET channel = 'app', app_score = 100 WHERE id = ANY(%s)", (app_ids,))
        if pc_ids:
            cr.execute("UPDATE igarage_usage_item SET channel = 'pc', app_score = 0 WHERE id = ANY(%s)", (pc_ids,))
        Item.invalidate_model()
        cr.execute("SELECT DISTINCT ext_job_id FROM igarage_usage_item WHERE id = ANY(%s)", (pend.ids,))
        self._rebuild_jobs({r[0] for r in cr.fetchall() if r[0]})
        return len(rows)
