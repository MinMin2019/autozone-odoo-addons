# -*- coding: utf-8 -*-
"""ดึงผลคำนวณเงินเดือนจาก Business Plus (SQL Server) -> Excel สำหรับ wizard "Import Inputs (Excel)"

ใช้ได้ 2 ทาง (โค้ดชุดเดียวกัน):
  A. ปุ่ม "ดึงจาก Business Plus" ใน wizard บน Odoo (ตั้งค่าใน Settings › Technical › System Parameters:
     bplus.server / bplus.database / bplus.user / bplus.password [/ bplus.driver]) — ต้องมี pyodbc + ODBC Driver บน server
  B. สคริปต์บนเครื่องในออฟฟิศที่มองเห็น SQL Server:
        PYTHONUTF8=1 python bplus_extract.py --year 2026 --month 8 [--out D:\\payroll] [--ini path]
     ini (ค่าเริ่มต้น %USERPROFILE%\\bplus_extract.ini):
        [bplus]
        server = 192.168.100.5
        database = PayrollAutozone
        user = odoo_reader
        password = ...
        ; sqlcmd = C:\\...\\sqlcmd.exe   (ระบุถ้าหาเองไม่เจอ; ใช้เมื่อไม่มี pyodbc)

ตาราง map รหัส: bplus_map.json (สร้างจาก gen_payroll_config.py) โฟลเดอร์เดียวกับไฟล์นี้
ผลลัพธ์ payslip_inputs_<ปี>-<เดือน>.xlsx 4 ชีต: Import (wizard อ่าน) / Control (ยอดต่อคนไว้เทียบ NET) / Info / Skipped
หยุดทันที (ไม่สร้างไฟล์) ถ้าเจอรหัส BPlus ที่มียอด ≠ 0 แต่ไม่อยู่ใน map หรือสมการ รายได้-หัก-เงินกู้ ≠ สุทธิ
"""
import argparse
import configparser
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
MAP_PATH = os.path.join(HERE, 'bplus_map.json')
THAI_MONTHS = ['', 'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']

SQL_PERIODS = """SELECT PRP_KEY, PRP_PAYDATE, PRP_ST_DATE, PRP_EN_DATE,
       (SELECT COUNT(*) FROM PRRESULT r WHERE r.PRR_PRP = p.PRP_KEY) AS n_rows
FROM PRPERIOD p WHERE PRP_YEAR = {year} AND PRP_MONTH = {month} ORDER BY PRP_KEY"""

SQL_ROWS = """SELECT pi.PRS_NO, LTRIM(RTRIM(e.EMP_INTL)) AS EMP_INTL, LTRIM(RTRIM(e.EMP_NAME)) AS EMP_NAME,
       LTRIM(RTRIM(e.EMP_SURNME)) AS EMP_SURNME, d.DF_CODE, d.DF_DESC, d.DF_ORDER,
       r.PRR_QTY, r.PRR_AMT, r.PRR_PRP, br.BR_CODE, dp.DEPT_CODE
FROM PRRESULT r
JOIN PRDEFTAB d ON d.DF_KEY = r.PRR_DF
JOIN PERSONALINFO pi ON pi.PRS_EMP = r.PRR_EMP
JOIN EMPFILE e ON e.EMP_KEY = r.PRR_EMP
LEFT JOIN BRANCH br ON br.BR_KEY = r.PRR_BR
LEFT JOIN DEPTTAB dp ON dp.DEPT_KEY = r.PRR_DEPT
WHERE r.PRR_PRP IN ({keys})
ORDER BY pi.PRS_NO, d.DF_ORDER, d.DF_CODE"""


class ExtractError(Exception):
    """ข้อผิดพลาดที่ต้องให้คนแก้ก่อน (ข้อความภาษาไทยพร้อมแสดงผู้ใช้)"""


# ---------------------------------------------------------------------------
# การเชื่อมต่อ
# ---------------------------------------------------------------------------
class Db:
    def __init__(self, cfg, allow_sqlcmd=True):
        self.cfg = cfg
        self.mode = None
        try:
            import pyodbc  # noqa: F401
            self.mode = 'pyodbc'
        except ImportError:
            if not allow_sqlcmd:
                raise ExtractError('server นี้ยังไม่มี pyodbc — ติดตั้ง "ODBC Driver 17/18 for SQL Server" แล้ว pip install pyodbc')
            self.sqlcmd = cfg.get('sqlcmd') or self._find_sqlcmd()
            if not self.sqlcmd:
                raise ExtractError('ไม่พบ pyodbc และ sqlcmd — ติดตั้ง "ODBC Driver 17 for SQL Server" + sqlcmd หรือ pip install pyodbc')
            self.mode = 'sqlcmd'

    @staticmethod
    def _find_sqlcmd():
        p = shutil.which('sqlcmd')
        if p:
            return p
        for ver in ('180', '170', '160', '150'):
            for base in (r'C:\Program Files\Microsoft SQL Server\Client SDK\ODBC',
                         r'C:\Program Files (x86)\Microsoft SQL Server\Client SDK\ODBC'):
                cand = os.path.join(base, ver, 'Tools', 'Binn', 'sqlcmd.exe')
                if os.path.exists(cand):
                    return cand
        return None

    def query(self, sql):
        """คืน list ของ dict (คอลัมน์ -> str)"""
        if self.mode == 'pyodbc':
            return self._query_pyodbc(sql)
        return self._query_sqlcmd(sql)

    def _query_pyodbc(self, sql):
        import pyodbc
        driver = self.cfg.get('driver')
        if not driver:
            drivers = [d for d in pyodbc.drivers() if 'SQL Server' in d]
            driver = next((d for d in sorted(drivers, reverse=True) if 'ODBC Driver' in d),
                          drivers[0] if drivers else 'SQL Server')
        conn_str = (f"DRIVER={{{driver}}};SERVER={self.cfg['server']};DATABASE={self.cfg['database']};"
                    f"UID={self.cfg['user']};PWD={self.cfg['password']};TrustServerCertificate=yes;"
                    f"Encrypt=no;Connection Timeout=15")
        try:
            conn = pyodbc.connect(conn_str, timeout=15)
        except pyodbc.Error as e:
            raise ExtractError(f'ต่อ SQL Server {self.cfg["server"]} ไม่ได้ ({driver}): {e}')
        try:
            cur = conn.cursor()
            cur.execute(sql)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, ('' if v is None else str(v) for v in row))) for row in cur.fetchall()]
        finally:
            conn.close()

    def _query_sqlcmd(self, sql):
        fd, out = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        sep = '\x1f'
        cmd = [self.sqlcmd, '-S', self.cfg['server'], '-d', self.cfg['database'], '-U', self.cfg['user'],
               '-P', self.cfg['password'], '-l', '15', '-W', '-s', sep, '-u', '-o', out, '-C',
               '-Q', 'SET NOCOUNT ON; ' + sql]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            with open(out, encoding='utf-16') as f:
                text = f.read()
        except UnicodeError:
            with open(out, encoding='utf-8', errors='replace') as f:
                text = f.read()
        os.unlink(out)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if res.returncode != 0 or not lines or lines[0].startswith(('Msg ', 'Sqlcmd:', 'HResult')):
            raise ExtractError('sqlcmd ล้มเหลว:\n' + text + res.stderr)
        header = [h.strip() for h in lines[0].split(sep)]
        rows = []
        for ln in lines[2:]:  # ข้ามบรรทัดขีด
            vals = [v.strip() for v in ln.split(sep)]
            rows.append(dict(zip(header, (('' if v == 'NULL' else v) for v in vals))))
        return rows


def num(s):
    try:
        return float(str(s).replace(',', '') or 0)
    except ValueError:
        return 0.0


def pdate(s):
    s = str(s)[:10]
    return dt.date.fromisoformat(s) if s else None


def load_map(path=MAP_PATH):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# แกนกลาง: ดึง + ตรวจ + สร้าง workbook (ใช้ทั้งจาก CLI และ wizard)
# ---------------------------------------------------------------------------
def extract(cfg, year, month, mapping=None, allow_sqlcmd=True, log=print, loan_source='module'):
    """คืน dict: workbook (openpyxl), summary (ตัวเลข), period (วันที่งวด), batch_name
    loan_source: 'module' = เงินกู้ (BPlus 2320) ไม่นำเข้า ให้ทะเบียนเงินกู้ Odoo หักเอง (ค่าเริ่มต้น)
                 'bplus'  = นำเข้า 2320 เป็น input LOAN ตามยอด Business Plus (ทะเบียนเงินกู้ใช้ดู/เทียบเท่านั้น)
    ทั้งสองโหมด ชีต Control เก็บยอดเงินกู้ BPlus ไว้ในคอลัมน์ "เงินกู้" เสมอ เพื่อให้ wizard เทียบกับทะเบียน
    โยน ExtractError เมื่อข้อมูลไม่พร้อม/ไม่ลงตัว — ไม่มีการเขียนไฟล์ในฟังก์ชันนี้"""
    if loan_source not in ('module', 'bplus'):
        raise ExtractError(f'loan_source ไม่ถูกต้อง: {loan_source}')
    mapping = mapping or load_map()
    imp, skip = mapping['import'], mapping['skip']
    db = Db(cfg, allow_sqlcmd=allow_sqlcmd)
    log(f'เชื่อมต่อ {cfg["server"]}/{cfg["database"]} ด้วย {db.mode}')

    # 1) งวด (บางเดือนมี 2 key — รวมเฉพาะ key ที่มีข้อมูล)
    periods = [p for p in db.query(SQL_PERIODS.format(year=int(year), month=int(month))) if int(num(p['n_rows'])) > 0]
    if not periods:
        raise ExtractError(f'ไม่พบงวด {month}/{year} ที่มีผลคำนวณใน Business Plus (HR ยังไม่ปิดงวด หรือใส่เดือนผิด — เดือนของงวด = เดือนที่จ่าย)')
    keys = ','.join(p['PRP_KEY'] for p in periods)
    pay_date = pdate(periods[0]['PRP_PAYDATE'])
    d_start, d_end = pdate(periods[0]['PRP_ST_DATE']), pdate(periods[0]['PRP_EN_DATE'])
    log(f'งวด key {keys}: {d_start} → {d_end} จ่าย {pay_date} ({sum(int(num(p["n_rows"])) for p in periods)} แถว)')

    # 2) ข้อมูลรายบรรทัด
    rows = db.query(SQL_ROWS.format(keys=keys))

    # 3) แยกตาม map
    import_rows, skipped_rows = [], []
    unmapped = defaultdict(lambda: {'n': 0, 'amt': 0.0, 'desc': ''})
    ctl = defaultdict(lambda: {'earning': 0.0, 'deduction': 0.0, 'loan': 0.0, 'net': 0.0,
                               'tax_calc': 0.0, 'sso_employer': 0.0, 'name': '', 'br': '', 'dept': ''})
    for r in rows:
        emp = r['PRS_NO'].strip()
        code = str(int(num(r['DF_CODE'])))
        amt = num(r['PRR_AMT'])
        qty = num(r['PRR_QTY'])
        name = ' '.join(x for x in (r['EMP_NAME'], r['EMP_SURNME']) if x and x != '-')
        c = ctl[emp]
        c['name'] = name
        c['br'] = c['br'] or r.get('BR_CODE', '')
        c['dept'] = c['dept'] or r.get('DEPT_CODE', '')
        if code in skip:
            if code == '15':
                c['net'] += amt
            elif code == '29':
                c['tax_calc'] += amt
            skipped_rows.append((emp, name, code, r['DF_DESC'], qty, amt, skip[code]))
            continue
        m = imp.get(code)
        if not m:
            if amt:
                u = unmapped[code]
                u['n'] += 1
                u['amt'] += amt
                u['desc'] = r['DF_DESC']
            else:
                skipped_rows.append((emp, name, code, r['DF_DESC'], qty, amt, 'ไม่มีใน map ยอด 0'))
            continue
        if m['kind'] == 'loan':
            c['loan'] += amt
            if loan_source == 'bplus' and amt > 0:
                import_rows.append((emp, name, m['code'], amt, f'BPlus {code} {r["DF_DESC"]} (หักตาม Business Plus)'))
            else:
                skipped_rows.append((emp, name, code, r['DF_DESC'], qty, amt,
                                     'เงินกู้ - ทะเบียนเงินกู้ Odoo หักเอง' if loan_source == 'module' else 'ยอด 0'))
            continue
        if not amt:
            skipped_rows.append((emp, name, code, r['DF_DESC'], qty, amt, 'ยอด 0'))
            continue
        if amt < 0:
            raise ExtractError(f'พนักงาน {emp} รหัส {code} {r["DF_DESC"]} ยอดติดลบ {amt:,.2f} — ระบบรับเฉพาะค่าบวก ต้องตรวจใน Business Plus ก่อน')
        if m['kind'] == 'company':
            c['sso_employer'] += amt
        else:
            c[m['kind']] += amt
        note = f'BPlus {code} {r["DF_DESC"]}'
        if qty and qty != amt and qty != 1:
            note += f' (จำนวน {qty:g})'
        import_rows.append((emp, name, m['code'], amt, note))

    if unmapped:
        lines = [f'{code} {u["desc"]} ({u["n"]} แถว รวม {u["amt"]:,.2f})'
                 for code, u in sorted(unmapped.items(), key=lambda x: int(x[0]))]
        raise ExtractError('พบรหัส Business Plus ที่มียอดเงินแต่ไม่อยู่ในตาราง map — ต้องเพิ่มใน gen_payroll_config.py แล้ว generate + upgrade ก่อน:\n'
                           + '\n'.join(lines))

    # 4) ตรวจสมการต่อคน: รายได้ - รายการหัก - เงินกู้ = สุทธิ BPlus
    bad = []
    for emp, c in ctl.items():
        calc = c['earning'] - c['deduction'] - c['loan']
        if abs(calc - c['net']) > 0.005:
            bad.append(f'{emp} {c["name"]}: ได้ {c["earning"]:,.2f} หัก {c["deduction"]:,.2f} กู้ {c["loan"]:,.2f} '
                       f'สุทธิ {c["net"]:,.2f} ต่าง {calc - c["net"]:+,.2f}')
    if bad:
        raise ExtractError(f'ยอดไม่ลงตัว {len(bad)} คน (รายได้-หัก-เงินกู้ ≠ สุทธิ Business Plus) — อาจมีรหัสที่ map ผิดฝั่ง:\n'
                           + '\n'.join(bad[:20]) + ('\n...' if len(bad) > 20 else ''))

    # 5) workbook
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Import'
    ws.append(['รหัสพนักงาน (Registration Number)', 'ชื่อพนักงาน (ไว้ตรวจสอบ ปล่อยว่างได้)',
               'รหัสรายการ (Input Code)', 'จำนวนเงิน (ใส่ค่าบวกเสมอ)', 'ที่มา (Business Plus)'])
    for row in import_rows:
        ws.append(list(row))
    for col, w in zip('ABCDE', (18, 34, 22, 16, 44)):
        ws.column_dimensions[col].width = w

    wc = wb.create_sheet('Control')
    wc.append(['รหัสพนักงาน', 'ชื่อพนักงาน', 'รวมรายได้ (BPlus)', 'รวมรายการหัก (ไม่รวมเงินกู้)', 'เงินกู้ (BPlus 2320)',
               'สุทธิ (BPlus 15)', 'ภาษีที่โปรแกรมคำนวณ (29)', 'ปกส.นายจ้าง (8)', 'สาขา', 'แผนก'])
    for emp in sorted(ctl):
        c = ctl[emp]
        wc.append([emp, c['name'], c['earning'], c['deduction'], c['loan'], c['net'], c['tax_calc'], c['sso_employer'],
                   c['br'], c['dept']])
    for col, w in zip('ABCDEFGHIJ', (14, 34, 16, 20, 16, 16, 18, 14, 10, 10)):
        wc.column_dimensions[col].width = w

    tot = {'employees': len(ctl), 'lines': len(import_rows),
           'earning': sum(c['earning'] for c in ctl.values()),
           'deduction': sum(c['deduction'] for c in ctl.values()),
           'loan': sum(c['loan'] for c in ctl.values()),
           'net': sum(c['net'] for c in ctl.values())}
    batch_name = f'เงินเดือน {THAI_MONTHS[int(month)]} {int(year) + 543}'
    wi = wb.create_sheet('Info')
    for k, v in [('งวด', f'{THAI_MONTHS[int(month)]} {int(year) + 543} ({month}/{year})'),
                 ('ช่วงงวด (Batch date range)', f'{d_start} → {d_end}'), ('วันจ่าย', str(pay_date)),
                 ('PRP_KEY', keys), ('ต้นทาง', f'{cfg["server"]}/{cfg["database"]}'),
                 ('เงินกู้หักจาก', 'Business Plus (นำเข้าเป็น LOAN)' if loan_source == 'bplus' else 'ทะเบียนเงินกู้ Odoo (ไม่นำเข้า 2320)'),
                 ('ดึงเมื่อ', dt.datetime.now().strftime('%Y-%m-%d %H:%M')),
                 ('พนักงาน', tot['employees']), ('บรรทัดนำเข้า', tot['lines']),
                 ('รวมรายได้', tot['earning']), ('รวมรายการหัก (ไม่รวมเงินกู้)', tot['deduction']),
                 ('เงินกู้ (BPlus 2320)', tot['loan']), ('สุทธิ BPlus', tot['net']),
                 ('ตรวจ: รายได้-หัก-เงินกู้', tot['earning'] - tot['deduction'] - tot['loan'])]:
        wi.append([k, v])
    wi.column_dimensions['A'].width = 30
    wi.column_dimensions['B'].width = 40

    wsk = wb.create_sheet('Skipped')
    wsk.append(['รหัสพนักงาน', 'ชื่อ', 'BPlus code', 'รายการ', 'จำนวน', 'ยอดเงิน', 'เหตุผล'])
    for row in skipped_rows:
        wsk.append(list(row))
    for w_ in (ws, wc, wi, wsk):
        for cell in w_[1]:
            cell.font = Font(bold=True)

    log(f'พนักงาน {tot["employees"]} คน | นำเข้า {tot["lines"]} บรรทัด | รายได้ {tot["earning"]:,.2f} | '
        f'หัก {tot["deduction"]:,.2f} | เงินกู้ (ข้าม) {tot["loan"]:,.2f} | สุทธิ BPlus {tot["net"]:,.2f}')
    return {'workbook': wb, 'summary': tot, 'batch_name': batch_name,
            'period': {'keys': keys, 'date_start': d_start, 'date_end': d_end, 'pay_date': pay_date},
            'filename': f'payslip_inputs_{int(year)}-{int(month):02d}.xlsx'}


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='ดึงเงินเดือนจาก Business Plus เป็นไฟล์ import ของ Odoo')
    ap.add_argument('--year', type=int, required=True, help='ปี ค.ศ. ของงวด (PRP_YEAR)')
    ap.add_argument('--month', type=int, required=True, help='เดือนของงวด 1-12 (PRP_MONTH)')
    ap.add_argument('--out', default=os.getcwd(), help='โฟลเดอร์ปลายทาง (ค่าเริ่มต้น: โฟลเดอร์ปัจจุบัน)')
    ap.add_argument('--ini', default=os.path.join(os.path.expanduser('~'), 'bplus_extract.ini'))
    ap.add_argument('--map', default=MAP_PATH)
    ap.add_argument('--loan-source', choices=('module', 'bplus'), default='module',
                    help='module = ทะเบียนเงินกู้ Odoo หักเอง (ค่าเริ่มต้น) / bplus = นำเข้ายอดเงินกู้จาก Business Plus เป็น LOAN')
    args = ap.parse_args()

    if not os.path.exists(args.ini):
        sys.exit(f'ไม่พบไฟล์ตั้งค่า {args.ini} (ดูรูปแบบในหัวสคริปต์)')
    ini = configparser.ConfigParser()
    ini.read(args.ini, encoding='utf-8')
    cfg = dict(ini['bplus'])
    for k in ('server', 'database', 'user', 'password'):
        if not cfg.get(k):
            sys.exit(f'ini ขาดค่า {k}')
    try:
        res = extract(cfg, args.year, args.month, mapping=load_map(args.map), loan_source=args.loan_source)
    except ExtractError as e:
        sys.exit(f'\n!!! {e}')
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, res['filename'])
    res['workbook'].save(path)
    p = res['period']
    print(f'Batch ใน Odoo: ชื่อ "{res["batch_name"]}" ช่วง {p["date_start"]} → {p["date_end"]}')
    print('เขียนไฟล์:', path)


if __name__ == '__main__':
    main()
