# -*- coding: utf-8 -*-
"""ดึงผลคำนวณเงินเดือนจาก Business Plus (SQL Server) -> ไฟล์ Excel สำหรับ wizard "Import Inputs (Excel)"

รันบนเครื่องในออฟฟิศที่มองเห็น SQL Server (ไม่แตะ Odoo, อ่านอย่างเดียว):
    PYTHONUTF8=1 python bplus_extract.py --year 2026 --month 8 [--out D:\\payroll] [--ini path]

ตั้งค่าการเชื่อมต่อในไฟล์ ini (ค่าเริ่มต้น: %USERPROFILE%\\bplus_extract.ini):
    [bplus]
    server = 192.168.100.5
    database = PayrollAutozone
    user = odoo_reader
    password = ...
    ; sqlcmd = C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\sqlcmd.exe  (ระบุถ้าหาเองไม่เจอ)

การเชื่อมต่อ: ใช้ pyodbc ถ้ามี ไม่มีก็ใช้ sqlcmd (มากับ ODBC Driver 17/18) — ไม่ต้องลงอะไรเพิ่ม
ตาราง map รหัส: bplus_map.json (สร้างจาก gen_payroll_config.py) วางไว้โฟลเดอร์เดียวกับสคริปต์นี้

ผลลัพธ์ payslip_inputs_<ปี>-<เดือน>.xlsx มี 4 ชีต:
    Import  — รหัสพนักงาน / ชื่อ / Input Code / จำนวนเงิน / หมายเหตุ  (wizard อ่านคอลัมน์ A-D)
    Control — ยอดต่อคนจาก BPlus: รายได้ / รายการหัก / เงินกู้ / สุทธิ (wizard ใช้เทียบ NET หลังคำนวณ)
    Info    — งวด วันที่ ช่วงเวลา ยอดรวม
    Skipped — รหัสที่รู้จักแต่ไม่นำเข้า (สถิติ/ยอดสรุป) เผื่อสอบทาน
หยุดทำงานทันที (ไม่สร้างไฟล์) ถ้าเจอรหัส BPlus ที่มียอด ≠ 0 แต่ไม่อยู่ในตาราง map
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
# ถ้าฐานไม่มีตาราง BRANCH/DEPARTMENT (ชื่อต่างไป) จะ fallback เป็น query ไม่ join สาขา/แผนก
SQL_ROWS_NOBR = SQL_ROWS.replace(", br.BR_CODE, dp.DEPT_CODE", ", NULL AS BR_CODE, NULL AS DEPT_CODE") \
    .replace("LEFT JOIN BRANCH br ON br.BR_KEY = r.PRR_BR\n", "").replace("LEFT JOIN DEPTTAB dp ON dp.DEPT_KEY = r.PRR_DEPT\n", "")


# ---------------------------------------------------------------------------
# การเชื่อมต่อ
# ---------------------------------------------------------------------------
class Db:
    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = None
        try:
            import pyodbc  # noqa: F401
            self.mode = 'pyodbc'
        except ImportError:
            self.sqlcmd = cfg.get('sqlcmd') or self._find_sqlcmd()
            if not self.sqlcmd:
                sys.exit('ไม่พบ pyodbc และ sqlcmd — ติดตั้ง "ODBC Driver 17 for SQL Server" + "sqlcmd" หรือ pip install pyodbc')
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
        """คืน list ของ dict (คอลัมน์ -> str) — ค่าตัวเลขแปลงเองที่ผู้เรียก"""
        if self.mode == 'pyodbc':
            return self._query_pyodbc(sql)
        return self._query_sqlcmd(sql)

    def _query_pyodbc(self, sql):
        import pyodbc
        drivers = [d for d in pyodbc.drivers() if 'SQL Server' in d]
        driver = next((d for d in drivers if 'ODBC Driver' in d), drivers[0] if drivers else 'SQL Server')
        conn = pyodbc.connect(f"DRIVER={{{driver}}};SERVER={self.cfg['server']};DATABASE={self.cfg['database']};"
                              f"UID={self.cfg['user']};PWD={self.cfg['password']};TrustServerCertificate=yes")
        cur = conn.cursor()
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, ('' if v is None else str(v) for v in row))) for row in cur.fetchall()]
        conn.close()
        return rows

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
            sys.exit('sqlcmd ล้มเหลว:\n' + text + res.stderr)
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


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='ดึงเงินเดือนจาก Business Plus เป็นไฟล์ import ของ Odoo')
    ap.add_argument('--year', type=int, required=True, help='ปี ค.ศ. ของงวด (PRP_YEAR)')
    ap.add_argument('--month', type=int, required=True, help='เดือนของงวด 1-12 (PRP_MONTH)')
    ap.add_argument('--out', default=os.getcwd(), help='โฟลเดอร์ปลายทาง (ค่าเริ่มต้น: โฟลเดอร์ปัจจุบัน)')
    ap.add_argument('--ini', default=os.path.join(os.path.expanduser('~'), 'bplus_extract.ini'))
    ap.add_argument('--map', default=os.path.join(HERE, 'bplus_map.json'))
    args = ap.parse_args()

    if not os.path.exists(args.ini):
        sys.exit(f'ไม่พบไฟล์ตั้งค่า {args.ini} (ดูรูปแบบในหัวสคริปต์)')
    ini = configparser.ConfigParser()
    ini.read(args.ini, encoding='utf-8')
    cfg = dict(ini['bplus'])
    for k in ('server', 'database', 'user', 'password'):
        if not cfg.get(k):
            sys.exit(f'ini ขาดค่า {k}')
    with open(args.map, encoding='utf-8') as f:
        mp = json.load(f)
    imp, skip = mp['import'], mp['skip']

    db = Db(cfg)
    print(f'เชื่อมต่อ {cfg["server"]}/{cfg["database"]} ด้วย {db.mode}')

    # 1) งวด
    periods = db.query(SQL_PERIODS.format(year=args.year, month=args.month))
    periods = [p for p in periods if int(num(p['n_rows'])) > 0]
    if not periods:
        sys.exit(f'ไม่พบงวด {args.month}/{args.year} ที่มีผลคำนวณใน PRRESULT (HR ยังไม่ปิดงวด?)')
    keys = ','.join(p['PRP_KEY'] for p in periods)
    pay_date = pdate(periods[0]['PRP_PAYDATE'])
    d_start, d_end = pdate(periods[0]['PRP_ST_DATE']), pdate(periods[0]['PRP_EN_DATE'])
    print(f'งวด key {keys}: {d_start} → {d_end} จ่าย {pay_date} ({sum(int(num(p["n_rows"])) for p in periods)} แถว)')

    # 2) ข้อมูลรายบรรทัด
    try:
        rows = db.query(SQL_ROWS.format(keys=keys))
    except SystemExit:
        rows = db.query(SQL_ROWS_NOBR.format(keys=keys))

    # 3) แยกตาม map
    import_rows, skipped_rows, unmapped = [], [], defaultdict(lambda: {'n': 0, 'amt': 0.0, 'desc': ''})
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
            skipped_rows.append((emp, name, code, r['DF_DESC'], qty, amt, 'เงินกู้ - โมดูลเงินกู้หักเอง'))
            continue
        if not amt:
            skipped_rows.append((emp, name, code, r['DF_DESC'], qty, amt, 'ยอด 0'))
            continue
        if amt < 0:
            sys.exit(f'พนักงาน {emp} รหัส {code} {r["DF_DESC"]} ยอดติดลบ {amt} — wizard รับเฉพาะค่าบวก ต้องตรวจใน BPlus ก่อน')
        if m['kind'] == 'company':
            c['sso_employer'] += amt
        else:
            c[m['kind']] += amt
        note = f'BPlus {code} {r["DF_DESC"]}'
        if qty and qty != amt and qty != 1:
            note += f' (จำนวน {qty:g})'
        import_rows.append((emp, name, m['code'], amt, note))

    if unmapped:
        print('\n!!! พบรหัส Business Plus ที่มียอดเงินแต่ไม่อยู่ในตาราง map — เพิ่มใน gen_payroll_config.py แล้ว generate ใหม่ก่อน:')
        for code, u in sorted(unmapped.items(), key=lambda x: int(x[0])):
            print(f'   {code:>6}  {u["desc"]:<40} {u["n"]:>4} แถว  รวม {u["amt"]:>14,.2f}')
        sys.exit(2)

    # 4) ตรวจสมการต่อคน: รายได้ - รายการหัก - เงินกู้ = สุทธิ BPlus
    bad = []
    for emp, c in ctl.items():
        calc = c['earning'] - c['deduction'] - c['loan']
        if abs(calc - c['net']) > 0.005:
            bad.append((emp, c['name'], c['earning'], c['deduction'], c['loan'], c['net'], calc - c['net']))
    if bad:
        print(f'\n!!! ยอดไม่ลงตัว {len(bad)} คน (รายได้-หัก-เงินกู้ ≠ สุทธิ BPlus) — อาจมีรหัสที่ map ผิดฝั่ง:')
        for b in bad[:20]:
            print(f'   {b[0]} {b[1]:<30} ได้ {b[2]:>12,.2f} หัก {b[3]:>11,.2f} กู้ {b[4]:>10,.2f} สุทธิ {b[5]:>12,.2f} ต่าง {b[6]:>10,.2f}')
        sys.exit(3)

    # 5) เขียน Excel
    try:
        import openpyxl
        from openpyxl.styles import Font
    except ImportError:
        sys.exit('ต้อง pip install openpyxl')
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

    wi = wb.create_sheet('Info')
    tot_e = sum(c['earning'] for c in ctl.values())
    tot_d = sum(c['deduction'] for c in ctl.values())
    tot_l = sum(c['loan'] for c in ctl.values())
    tot_n = sum(c['net'] for c in ctl.values())
    for k, v in [('งวด', f'{THAI_MONTHS[args.month]} {args.year + 543} ({args.month}/{args.year})'),
                 ('ช่วงงวด (Batch date range)', f'{d_start} → {d_end}'), ('วันจ่าย', str(pay_date)),
                 ('PRP_KEY', keys), ('ต้นทาง', f'{cfg["server"]}/{cfg["database"]}'),
                 ('ดึงเมื่อ', dt.datetime.now().strftime('%Y-%m-%d %H:%M')),
                 ('พนักงาน', len(ctl)), ('บรรทัดนำเข้า', len(import_rows)),
                 ('รวมรายได้', tot_e), ('รวมรายการหัก (ไม่รวมเงินกู้)', tot_d), ('เงินกู้ (ไม่นำเข้า)', tot_l),
                 ('สุทธิ BPlus', tot_n), ('ตรวจ: รายได้-หัก-เงินกู้', tot_e - tot_d - tot_l)]:
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

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f'payslip_inputs_{args.year}-{args.month:02d}.xlsx')
    wb.save(path)
    print(f'\nพนักงาน {len(ctl)} คน | นำเข้า {len(import_rows)} บรรทัด | รายได้ {tot_e:,.2f} | หัก {tot_d:,.2f} | '
          f'เงินกู้ (ข้าม) {tot_l:,.2f} | สุทธิ BPlus {tot_n:,.2f}')
    print('Batch ใน Odoo: ชื่อ "เงินเดือน %s %s" ช่วง %s → %s' % (THAI_MONTHS[args.month], args.year + 543, d_start, d_end))
    print('เขียนไฟล์:', path)


if __name__ == '__main__':
    main()
