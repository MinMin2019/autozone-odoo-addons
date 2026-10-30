# -*- coding: utf-8 -*-
"""ตารางผลลัพธ์ของการติดตามการใช้แอปลงเวลาช่าง iGarage

ทุกตารางเป็นข้อมูลสำเนา (อ่านอย่างเดียวใน UI) — เขียนโดยตัวดึงข้อมูลใน igarage_sync.py เท่านั้น

คะแนน (app_score / ontime_score) เก็บเป็น 100 / 0 / ว่าง แล้วให้ pivot เฉลี่ย (aggregator=avg)
ค่าเฉลี่ยที่ได้จึงเป็น % ทันที และแถวที่ "ยังไม่รู้" (ว่าง) จะไม่ถูกนับในตัวหาร
"""
from odoo import fields, models, tools

CHANNELS_ITEM = [
    ('app', 'แอปมือถือ'),
    ('pc', 'PC'),
    ('pending', 'ไม่มีข้อมูล log'),
]
CHANNELS_JOB = [
    ('app', 'แอปล้วน'),
    ('pc', 'PC ล้วน'),
    ('mixed', 'ผสมแอป+PC'),
    ('pending', 'ไม่มีข้อมูล log'),
]


class IgarageUsageItem(models.Model):
    _name = 'igarage.usage.item'
    _description = 'iGarage: ชิ้นงาน (การลงเวลา)'
    _order = 'started desc, id desc'
    _rec_name = 'job_ref'

    ext_item_id = fields.Integer('รหัสชิ้นงาน iGarage', required=True, index=True, readonly=True)
    ext_job_id = fields.Integer('รหัสจ๊อบ iGarage', index=True, readonly=True)
    job_ref = fields.Char('เลขจ๊อบ', readonly=True)
    branch_code = fields.Char('สาขา', index=True, readonly=True)
    branch_name = fields.Char('ชื่อสาขา', readonly=True)
    date = fields.Date('วันที่เริ่ม', index=True, readonly=True)
    started = fields.Datetime('กดเริ่ม', readonly=True)
    finished = fields.Datetime('กดจบ', readonly=True)
    recorder_ext_id = fields.Integer('รหัสผู้บันทึก iGarage', index=True, readonly=True)
    recorder_name = fields.Char('ผู้บันทึก', readonly=True)
    worker_ext_id = fields.Integer('รหัสช่าง iGarage', index=True, readonly=True)
    worker_name = fields.Char('ช่าง', readonly=True)
    worker_code = fields.Char('รหัสช่าง', readonly=True)
    is_dummy = fields.Boolean('บาร์โค้ดสำรอง/Dummy', readonly=True)
    channel = fields.Selection(CHANNELS_ITEM, 'ช่องทาง', index=True, readonly=True)
    measurable = fields.Boolean('วัดได้', readonly=True, help='มีทั้งกดเริ่มและกดจบ')
    item_count = fields.Integer('จำนวนชิ้น', default=1, readonly=True, aggregator='sum')
    app_score = fields.Float('ใช้แอป (%)', digits=(5, 1), aggregator='avg', readonly=True)
    ontime_score = fields.Float(
        'ลงเวลาตรง (%)', digits=(5, 1), aggregator='avg', readonly=True,
        help='กดเริ่มกับกดจบห่างกันเกิน 60 วินาที — ไม่ได้แปลว่าเวลาที่บันทึกตรงกับความจริง')

    _sql_constraints = [('ext_item_uniq', 'unique(ext_item_id)', 'ชิ้นงาน iGarage ซ้ำ')]


class IgarageUsageJob(models.Model):
    _name = 'igarage.usage.job'
    _description = 'iGarage: จ๊อบ (การลงเวลา)'
    _order = 'date desc, id desc'
    _rec_name = 'job_ref'

    ext_job_id = fields.Integer('รหัสจ๊อบ iGarage', required=True, index=True, readonly=True)
    job_ref = fields.Char('เลขจ๊อบ', readonly=True)
    branch_code = fields.Char('สาขา', index=True, readonly=True)
    branch_name = fields.Char('ชื่อสาขา', readonly=True)
    date = fields.Date('วันที่เริ่ม', index=True, readonly=True)
    item_count = fields.Integer('จำนวนชิ้น', readonly=True, aggregator='sum')
    app_item_count = fields.Integer('ชิ้นที่ผ่านแอป', readonly=True, aggregator='sum')
    job_count = fields.Integer('จำนวนจ๊อบ', default=1, readonly=True, aggregator='sum')
    channel = fields.Selection(CHANNELS_JOB, 'ช่องทาง', index=True, readonly=True)
    measurable = fields.Boolean('วัดได้', readonly=True)
    app_score = fields.Float(
        'ใช้แอป (%)', digits=(5, 1), aggregator='avg', readonly=True,
        help='จ๊อบที่มีอย่างน้อย 1 ชิ้นบันทึกผ่านแอป')
    ontime_score = fields.Float(
        'ลงเวลาตรง (%)', digits=(5, 1), aggregator='avg', readonly=True,
        help='เริ่มชิ้นแรกถึงจบชิ้นสุดท้ายของจ๊อบห่างกันเกิน 60 วินาที '
             '(ชิ้นที่กดพร้อมกันในจ๊อบเดียวกันถือว่าทำไปด้วยกัน)')

    _sql_constraints = [('ext_job_uniq', 'unique(ext_job_id)', 'จ๊อบ iGarage ซ้ำ')]

    def action_open_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'ชิ้นงานของจ๊อบ %s' % (self.job_ref or self.ext_job_id),
            'res_model': 'igarage.usage.item',
            'view_mode': 'list',
            'domain': [('ext_job_id', '=', self.ext_job_id)],
        }


class IgarageUsageJobWorker(models.Model):
    _name = 'igarage.usage.job.worker'
    _description = 'iGarage: จ๊อบ x ช่าง'
    _order = 'date desc, id desc'
    _rec_name = 'worker_name'

    ext_job_id = fields.Integer('รหัสจ๊อบ iGarage', required=True, index=True, readonly=True)
    worker_ext_id = fields.Integer('รหัสช่าง iGarage', required=True, index=True, readonly=True)
    job_ref = fields.Char('เลขจ๊อบ', readonly=True)
    branch_code = fields.Char('สาขา', index=True, readonly=True)
    branch_name = fields.Char('ชื่อสาขา', readonly=True)
    date = fields.Date('วันที่เริ่ม', index=True, readonly=True)
    worker_name = fields.Char('ช่าง', readonly=True)
    worker_code = fields.Char('รหัสช่าง', readonly=True)
    is_dummy = fields.Boolean('บาร์โค้ดสำรอง/Dummy', readonly=True)
    item_count = fields.Integer('จำนวนชิ้น', readonly=True, aggregator='sum')
    job_count = fields.Integer('จำนวนจ๊อบ', default=1, readonly=True, aggregator='sum')
    app_score = fields.Float('ใช้แอป (%)', digits=(5, 1), aggregator='avg', readonly=True)
    ontime_score = fields.Float('ลงเวลาตรง (%)', digits=(5, 1), aggregator='avg', readonly=True)

    _sql_constraints = [('ext_job_worker_uniq', 'unique(ext_job_id, worker_ext_id)', 'จ๊อบ x ช่าง ซ้ำ')]


class IgarageUsageAppMark(models.Model):
    """วินาทีที่แอปยิงคำสั่งลงเวลาเข้ามา (จาก log เว็บ) ต่อโปรไฟล์ผู้บันทึก — ใช้จับคู่กับชิ้นงาน"""
    _name = 'igarage.usage.appmark'
    _description = 'iGarage: เวลาที่แอปสั่งลงเวลา'
    _order = 'ts desc'

    recorder_ext_id = fields.Integer('รหัสผู้บันทึก iGarage', index=True, readonly=True)
    ts = fields.Datetime('เวลา', index=True, readonly=True)

    _sql_constraints = [('mark_uniq', 'unique(recorder_ext_id, ts)', 'ซ้ำ')]


class IgarageUsageLogFile(models.Model):
    _name = 'igarage.usage.logfile'
    _description = 'iGarage: ไฟล์ log เว็บที่ประมวลผลแล้ว'
    _order = 'last_ts desc, id desc'

    name = fields.Char('ชื่อไฟล์ (ตอนประมวลผล)', readonly=True)
    modify = fields.Char('เวลาแก้ไขไฟล์บน server', readonly=True)
    size = fields.Integer('ขนาด (byte)', readonly=True)
    first_ts = fields.Datetime('บรรทัดแรก', readonly=True)
    last_ts = fields.Datetime('บรรทัดสุดท้าย', readonly=True)
    api_calls = fields.Integer('เรียก API ลงเวลา', readonly=True)
    app_writes = fields.Integer('คำสั่งลงเวลาจากแอป', readonly=True)
    unknown_keys = fields.Integer('คีย์ที่จับคู่บัญชีไม่ได้', readonly=True)

    _sql_constraints = [('file_uniq', 'unique(modify, size)', 'ไฟล์นี้ประมวลผลแล้ว')]


class IgarageUsageSyncLog(models.Model):
    _name = 'igarage.usage.sync.log'
    _description = 'iGarage: ประวัติการดึงข้อมูล'
    _order = 'id desc'

    name = fields.Char('รอบการดึง', readonly=True)
    kind = fields.Selection(
        [('db', 'ฐานข้อมูล iGarage'), ('db_full', 'ฐานข้อมูล iGarage (ดึงใหม่ทั้งหมด)'),
         ('log', 'log เว็บเซิร์ฟเวอร์')],
        'ดึงอะไร', readonly=True)
    trigger = fields.Selection([('cron', 'อัตโนมัติ'), ('manual', 'สั่งเอง')], 'สั่งโดย', readonly=True)
    state = fields.Selection(
        [('done', 'สำเร็จ'), ('skip', 'ยังไม่ได้ตั้งค่า'), ('error', 'ล้มเหลว')], 'สถานะ', readonly=True)
    rows = fields.Integer('จำนวนรายการ', readonly=True)
    duration = fields.Float('ใช้เวลา (วินาที)', digits=(8, 1), readonly=True)
    message = fields.Text('รายละเอียด', readonly=True)


class IgarageUsageBranchMonth(models.Model):
    """ภาพรวมรายสาขารายเดือน (SQL view) + แถว "รวมทุกสาขา" ของแต่ละเดือน

    ตัวเลขคำนวณจากจ๊อบจริงในเดือนนั้น (ไม่ใช่เฉลี่ยของเฉลี่ย) และนับช่างแบบไม่ซ้ำคน
    ต้องประกาศหลังตาราง job และ job.worker เพราะ view อ่านสองตารางนั้น
    """
    _name = 'igarage.usage.branch.month'
    _description = 'iGarage: ภาพรวมรายสาขารายเดือน'
    _auto = False
    _order = 'month desc, is_total desc, app_pct desc, job_count desc'
    _rec_name = 'branch_code'

    month = fields.Date('เดือน', readonly=True)
    is_total = fields.Boolean('แถวรวม', readonly=True)
    branch_code = fields.Char('สาขา', readonly=True)
    branch_name = fields.Char('ชื่อสาขา', readonly=True)
    job_count = fields.Integer('จ๊อบ', readonly=True)
    app_job_count = fields.Integer('จ๊อบที่ใช้แอป', readonly=True)
    app_pct = fields.Float('ใช้แอป (%)', digits=(5, 1), readonly=True)
    ontime_pct = fields.Float('ลงเวลาตรง (%)', digits=(5, 1), readonly=True)
    app_ontime_pct = fields.Float('ตรง: แอป (%)', digits=(5, 1), readonly=True,
                                  help='ลงเวลาตรงของจ๊อบที่บันทึกผ่านแอปล้วน')
    pc_ontime_pct = fields.Float('ตรง: PC (%)', digits=(5, 1), readonly=True,
                                 help='ลงเวลาตรงของจ๊อบที่บันทึกผ่าน PC ล้วน')
    diff_pct = fields.Float('แอป−PC', digits=(5, 1), readonly=True,
                            help='ตรง: แอป ลบ ตรง: PC — บวก = จ๊อบที่ผ่านแอปลงเวลาตรงกว่า')
    has_app = fields.Boolean(readonly=True)
    has_pc = fields.Boolean(readonly=True)
    worker_count = fields.Integer('ช่างทั้งหมด', readonly=True,
                                  help='ช่างที่มีงานในเดือนนั้น นับไม่ซ้ำคน ไม่รวมบาร์โค้ดสำรอง/Dummy')
    app_worker_count = fields.Integer('ช่างที่ใช้แอป', readonly=True,
                                      help='ช่างที่มีอย่างน้อย 1 จ๊อบบันทึกผ่านแอปในเดือนนั้น')
    workers_display = fields.Char('ช่างที่ใช้แอป', readonly=True,
                                  help='ช่างที่ใช้แอป / ช่างทั้งหมด (นับไม่ซ้ำคน ไม่รวมบาร์โค้ดสำรอง/Dummy)')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW igarage_usage_branch_month AS
            WITH j AS (
                SELECT date_trunc('month', date)::date                              AS month,
                       GROUPING(branch_code) = 1                                    AS is_total,
                       branch_code,
                       MAX(branch_name)                                             AS branch_name,
                       COUNT(*)                                                     AS job_count,
                       COUNT(*) FILTER (WHERE app_score = 100)                      AS app_job_count,
                       AVG(app_score)                                               AS app_pct,
                       AVG(ontime_score)                                            AS ontime_pct,
                       AVG(ontime_score) FILTER (WHERE channel = 'app')             AS app_ontime_pct,
                       AVG(ontime_score) FILTER (WHERE channel = 'pc')              AS pc_ontime_pct
                  FROM igarage_usage_job
                 WHERE date IS NOT NULL
                 GROUP BY GROUPING SETS ((date_trunc('month', date), branch_code),
                                         (date_trunc('month', date)))
            ), w AS (
                SELECT date_trunc('month', date)::date                              AS month,
                       GROUPING(branch_code) = 1                                    AS is_total,
                       branch_code,
                       COUNT(DISTINCT worker_ext_id)                                AS worker_count,
                       COUNT(DISTINCT worker_ext_id) FILTER (WHERE app_score = 100) AS app_worker_count
                  FROM igarage_usage_job_worker
                 WHERE date IS NOT NULL AND NOT COALESCE(is_dummy, FALSE)
                 GROUP BY GROUPING SETS ((date_trunc('month', date), branch_code),
                                         (date_trunc('month', date)))
            )
            SELECT ((EXTRACT(YEAR FROM j.month) * 100 + EXTRACT(MONTH FROM j.month)) * 10000
                    + ROW_NUMBER() OVER (PARTITION BY j.month ORDER BY j.is_total DESC, j.branch_code))::int AS id,
                   j.month,
                   j.is_total,
                   CASE WHEN j.is_total THEN 'รวมทุกสาขา' ELSE j.branch_code END AS branch_code,
                   CASE WHEN j.is_total THEN NULL ELSE j.branch_name END         AS branch_name,
                   j.job_count, j.app_job_count, j.app_pct, j.ontime_pct,
                   j.app_ontime_pct, j.pc_ontime_pct,
                   j.app_ontime_pct - j.pc_ontime_pct                            AS diff_pct,
                   j.app_ontime_pct IS NOT NULL                                  AS has_app,
                   j.pc_ontime_pct IS NOT NULL                                   AS has_pc,
                   COALESCE(w.worker_count, 0)                                   AS worker_count,
                   COALESCE(w.app_worker_count, 0)                               AS app_worker_count,
                   COALESCE(w.app_worker_count, 0) || '/' || COALESCE(w.worker_count, 0) AS workers_display
              FROM j
              LEFT JOIN w ON w.month = j.month AND w.is_total = j.is_total
                         AND COALESCE(w.branch_code, '') = COALESCE(j.branch_code, '')
        """)


class IgarageUsageWorkerMonth(models.Model):
    """สรุปรายช่างรายเดือน (SQL view) — ต้องประกาศหลัง igarage.usage.job.worker เพราะ view อ่านตารางนั้น"""
    _name = 'igarage.usage.worker.month'
    _description = 'iGarage: สรุปช่างรายเดือน'
    _auto = False
    _order = 'month desc, job_count desc'
    _rec_name = 'worker_name'

    month = fields.Date('เดือน', readonly=True)
    branch_code = fields.Char('สาขา', readonly=True)
    branch_name = fields.Char('ชื่อสาขา', readonly=True)
    worker_ext_id = fields.Integer('รหัสช่าง iGarage', readonly=True)
    worker_name = fields.Char('ช่าง', readonly=True)
    worker_code = fields.Char('รหัสช่าง', readonly=True)
    is_dummy = fields.Boolean('บาร์โค้ดสำรอง/Dummy', readonly=True)
    job_count = fields.Integer('จำนวนจ๊อบ', readonly=True, aggregator='sum')
    app_job_count = fields.Integer('จ๊อบที่ใช้แอป', readonly=True, aggregator='sum')
    app_pct = fields.Float('ใช้แอป (%)', digits=(5, 1), readonly=True, aggregator='avg')
    ontime_pct = fields.Float('ลงเวลาตรง (%)', digits=(5, 1), readonly=True, aggregator='avg')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW igarage_usage_worker_month AS
            SELECT MIN(w.id)                                         AS id,
                   date_trunc('month', w.date)::date                 AS month,
                   w.branch_code                                     AS branch_code,
                   MAX(w.branch_name)                                AS branch_name,
                   w.worker_ext_id                                   AS worker_ext_id,
                   MAX(w.worker_name)                                AS worker_name,
                   MAX(w.worker_code)                                AS worker_code,
                   BOOL_OR(w.is_dummy)                               AS is_dummy,
                   COUNT(*)                                          AS job_count,
                   COUNT(*) FILTER (WHERE w.app_score = 100)         AS app_job_count,
                   AVG(w.app_score)                                  AS app_pct,
                   AVG(w.ontime_score)                               AS ontime_pct
              FROM igarage_usage_job_worker w
             WHERE w.date IS NOT NULL
             GROUP BY date_trunc('month', w.date), w.branch_code, w.worker_ext_id
        """)
