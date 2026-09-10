# -*- coding: utf-8 -*-
"""Generator (v4 — 8 ก.ย. 2026): ตารางแม็ป Business Plus -> Odoo แบบ 1 รหัส = 1 input type
สร้าง 4 ไฟล์ (อย่าแก้ไฟล์ปลายทางด้วยมือ แก้ที่นี่แล้วรันใหม่):
  1. data/hr_payroll_structure_v3.xml   input types + 3 structures + rules
  2. tools/wire_payroll_accounts_shell.py ผูกบัญชี/ชื่อ/ลำดับ/รหัส ทุก rule + journal + ตั้งค่า
  3. tools/bplus_map.json                ตาราง BPlus DF_CODE -> Odoo code ให้ bplus_extract.py ใช้
  4. doc/BPLUS_CODE_MAP.md               ตารางให้บัญชีตรวจ

หลักการ (เคาะ 8 ก.ย. 2026):
  - สลิปแสดงทุกรายการแยกตามรหัส Business Plus (OT 4 อัตราแยกกัน ฯลฯ)
  - ใบสำคัญรวมตามบัญชีเอง (batch_payroll_move_lines) -> rule หลายตัวชี้บัญชีเดียวกันได้
  - rule ใหม่ใช้บัญชีของกลุ่มเดียวกันที่บัญชียืนยันไว้ 6 ส.ค. 2026 ไปก่อน (บัญชีปรับทีหลังได้ใน UI)
  - เงินกู้ (BPlus 2320) ไม่นำเข้า ใช้โมดูล custom_hr_loan | ภาษีใช้รหัส 13 ยอดหักจริง (29 ไม่นำเข้า)
กลไกเครื่องหมาย (จาก hr_payroll_account source):
  rule ยอดบวก + account_debit = Dr | rule ยอดลบ + account_debit = Cr
  ดังนั้น: รายได้ -> expense ใน DR ช่อง | รายการหัก(ลบ) -> บัญชีเป้าหมาย Cr ใส่ช่อง DR เช่นกัน
  NET(บวก) -> 232001 ใส่ช่อง CREDIT | SSO นายจ้าง(บวก) -> Dr expense + Cr 232010 สองช่อง"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
XML_OUT = os.path.join(MOD, 'data', 'hr_payroll_structure_v3.xml')
WIRE_OUT = os.path.join(HERE, 'wire_payroll_accounts_shell.py')
MAP_OUT = os.path.join(HERE, 'bplus_map.json')
DOC_OUT = os.path.join(MOD, 'doc', 'BPLUS_CODE_MAP.md')

G = ('fac', 'off', 'exe')  # โรงงาน / สำนักงาน / ผู้บริหาร

# reuse xmlid ของ input types ที่ประกาศไว้ใน hr_payslip_input_type_data.xml (โค้ดเดียวกัน)
EXISTING_TYPES = {'BASIC': 'input_type_basic', 'OT': 'input_type_ot', 'BONUS': 'input_type_bonus',
                  'DILIGENCE': 'input_type_diligence', 'INC_OTHER': 'input_type_inc_other',
                  'SSO': 'input_type_sso', 'TAX': 'input_type_tax', 'LATE': 'input_type_late',
                  'ADVANCE': 'input_type_advance', 'LOAN': 'input_type_loan',
                  'DED_OTHER': 'input_type_ded_other'}
# input types ที่เลิกใช้ (archive ใน wire script) — LOAN_INTEREST ถูกแทนด้วย LOAN_INT ของ custom_hr_loan
RETIRED_TYPE_XMLIDS = ['input_type_commission', 'input_type_allowance', 'input_type_pvd',
                       'input_type_loan_interest']

# บัญชีตามกลุ่ม (ฉบับบัญชียืนยัน 6 ส.ค. 2026) — รหัสใหม่หยิบชุดของกลุ่มเดียวกัน
A = {
    'SAL':   {'fac': '511000', 'off': '621001', 'exe': '621000'},   # เงินเดือน / ปรับลดเงินเดือน
    'OT':    {'fac': '511001', 'off': '621002', 'exe': '621002'},
    'COL':   {'fac': '511006', 'off': '621006', 'exe': '621006'},   # ค่าครองชีพ
    'MEAL':  {'fac': '512002', 'off': '622002', 'exe': '622002'},   # ค่าอาหาร
    'DIL':   {'fac': '511007', 'off': '621007', 'exe': '621007'},   # เบี้ยขยัน
    'WELF':  {'fac': '512008', 'off': '622009', 'exe': '622009'},   # สวัสดิการอื่น (พาหนะ/เช่าบ้าน/โทรศัพท์)
    'INCV':  {'fac': '511005', 'off': '621005', 'exe': '621005'},   # incentive
    'PDIEM': {'fac': '512003', 'off': '622003', 'exe': '622003'},   # เบี้ยเลี้ยง
    'PIECE': {'fac': '511003', 'off': '621001', 'exe': '621000'},   # รายชิ้น (สำนักงานไม่มี -> เงินเดือน)
    'POS':   {'fac': '511008', 'off': '621008', 'exe': '621008'},   # ค่าตำแหน่ง/วิชาชีพ
    'BON':   {'fac': '511010', 'off': '621010', 'exe': '621010'},
    'UNIF':  {'fac': '512004', 'off': '622004', 'exe': '622004'},
}
def same(code):
    return {g: code for g in G}

# ---------------------------------------------------------------------------
# ตารางหลัก: (BPlus DF_CODE หรือ None, Odoo code, ชื่อบนสลิป, บัญชี{group: acc}, หมายเหตุให้บัญชี)
# ลำดับในลิสต์ = ลำดับบรรทัดบนสลิป
# ---------------------------------------------------------------------------
EARNINGS = [
    (1,    'BASIC',           'เงินเดือน',                     A['SAL'],   ''),
    (1554, 'PAY_ADJUST',      'ตกหล่นเงินเดือน',               A['SAL'],   ''),
    (1110, 'OT_X1',           'ค่าล่วงเวลา x1',                A['OT'],    'เดิมรวมใน OT'),
    (1120, 'OT_X15',          'ค่าล่วงเวลา x1.5',              A['OT'],    'เดิมรวมใน OT'),
    (1130, 'OT_X2',           'ค่าล่วงเวลา x2',                A['OT'],    'เดิมรวมใน OT'),
    (1140, 'OT_X3',           'ค่าล่วงเวลา x3',                A['OT'],    'เดิมรวมใน OT'),
    (1150, 'OT',              'ค่าล่วงเวลา (ไม่ระบุอัตรา)',    A['OT'],    'BPlus ไม่ได้ใช้ เก็บไว้กรอกมือ'),
    (1230, 'POSITION',        'ค่าตำแหน่ง',                    A['POS'],   'เดิมชื่อ ค่าตำแหน่ง+วิชาชีพ'),
    (1553, 'PROFESSIONAL',    'ค่าวิชาชีพ',                    A['POS'],   'ใช้บัญชีค่าตำแหน่ง'),
    (1222, 'PROFESSIONAL_2',  'ค่าวิชาชีพ (2)',                A['POS'],   'BPlus มี "ค่าวิชาชีพ" 2 รหัส (1222/1553) ต่างกันอย่างไร-รอ HR'),
    (16,   'DILIGENCE',       'เบี้ยขยัน',                     A['DIL'],   'BPlus "เบี้ยขยัน(ตามสิทธิ)"'),
    (1410, 'DILIGENCE_EXTRA', 'เบี้ยขยัน (เพิ่มเติม)',         A['DIL'],   ''),
    (1240, 'COST_LIVING',     'ค่าครองชีพ',                    A['COL'],   ''),
    (1241, 'COST_LIVING_SSO', 'ค่าครองชีพ (SSO)',              A['COL'],   'ฐานประกันสังคม'),
    (1330, 'MEAL_OT',         'ค่าอาหาร',                      A['MEAL'],  ''),
    (1331, 'MEAL_FIX',        'ค่าอาหาร (ฝังในประวัติ)',       A['WELF'],  ''),
    (1520, 'TRANSPORT',       'ค่าพาหนะ',                      A['WELF'],  ''),
    (1320, 'HOUSE_RENT',      'ค่าเช่าบ้าน',                   A['WELF'],  ''),
    (1350, 'PHONE',           'ค่าโทรศัพท์',                   A['WELF'],  ''),
    (1530, 'PER_DIEM',        'เบี้ยเลี้ยง',                   A['PDIEM'], ''),
    (1552, 'INCENTIVE',       'Incentive',                     A['INCV'],  ''),
    (1571, 'PIECE_RATE',      'ค่าแรงรายชิ้น',                 A['PIECE'], ''),
    (1440, 'BONUS',           'โบนัส',                         A['BON'],   ''),
    (1441, 'BONUS_QTR',       'โบนัสไตรมาส',                   A['BON'],   ''),
    (1557, 'LEAVE_REFUND',    'คืนเงินพักร้อน',                A['SAL'],   ''),
    (1555, 'WELFARE_ADJUST',  'ตกหล่นสวัสดิการ',               A['SAL'],   ''),
    (None, 'UNIFORM_PAY',     'ค่าชุดฟอร์ม (จ่ายให้)',         A['UNIF'],  'ไม่มีใน BPlus เก็บไว้กรอกมือ'),
    (1556, 'DEPOSIT_REFUND',  'คืนเงินประกันพนักงาน',          same('232013'), 'ตัดหนี้สิน ไม่ใช่ค่าใช้จ่าย'),
    (1573, 'SEVERANCE',       'เงินชดเชยการเลิกจ้าง',          A['SAL'],   '★ บัญชีควรแยกบัญชีค่าชดเชย ตอนนี้ลงเงินเดือนไปก่อน'),
    (1550, 'INC_OTHER',       'เงินได้อื่น ๆ',                 A['SAL'],   ''),
]
DEDUCTIONS = [
    (7,     'SSO',               'หักประกันสังคม',                 same('232010'), ''),
    (13,    'TAX',               'หักภาษีเงินได้ (ภงด.1)',         same('231001'), 'ใช้ยอดหักจริง (BPlus 13) ไม่ใช่ 29'),
    (None,  'TAX_PREV_YEAR',     'หักค่าภาษีปีที่แล้ว',            same('154101'), 'ไม่มีใน BPlus'),
    (2240,  'STUDENT_LOAN',      'หัก กยศ.',                       same('232016'), ''),
    (2110,  'ABSENCE',           'หักขาดงาน',                      A['SAL'],       'เดิมชื่อ หักขาดงาน/ลา/มาสาย'),
    (2120,  'LATE',              'หักมาสาย',                       A['SAL'],       ''),
    (2430,  'EARLY_LEAVE',       'หักกลับก่อนเวลา',                A['SAL'],       ''),
    (2410,  'NO_SCAN_IN',        'หักไม่ตอกบัตรเข้า',              A['SAL'],       ''),
    (2420,  'NO_SCAN_OUT',       'หักไม่ตอกบัตรออก',               A['SAL'],       ''),
    (2150,  'PERSONAL_LEAVE',    'หักลากิจ',                       A['SAL'],       ''),
    (2151,  'PERSONAL_LEAVE_SP', 'หักลากิจ (พิเศษ)',               A['SAL'],       ''),
    (2130,  'SICK_NO_CERT',      'หักป่วยไม่มีใบแพทย์',            A['SAL'],       ''),
    (10028, 'SICK_OVER_QUOTA',   'หักลาป่วยเกินสิทธิ',             A['SAL'],       ''),
    (2170,  'MATERNITY',         'หักลาคลอด',                      A['SAL'],       ''),
    (2180,  'ORDINATION',        'หักลาบวช',                       A['SAL'],       ''),
    (2182,  'COMPANY_LEAVE',     'หักลาตามเงื่อนไขบริษัท',         A['SAL'],       ''),
    (2111,  'SALARY_CUT_25',     'หักเงินเดือน 25%',               A['SAL'],       ''),
    (2901,  'SUSPEND',           'หักพักงาน',                      A['SAL'],       ''),
    (2902,  'SUSPEND_TAX',       'หักพักงาน (คิดภาษี)',            A['SAL'],       ''),
    (2330,  'ADVANCE',           'หักเงินเบิกล่วงหน้า',            same('152101'), ''),
    (2320,  'LOAN',              'หักเงินกู้',                     same('154101'), 'มาจากโมดูลเงินกู้เท่านั้น ไม่นำเข้าจากไฟล์'),
    (None,  'LOAN_INT',          'หักดอกเบี้ยเงินกู้',             same('710002'), 'มาจากโมดูลเงินกู้ (input type ของ custom_hr_loan)'),
    (11,    'GUARANTEE',         'หักเงินค้ำประกันพนักงาน',        same('232013'), ''),
    (2210,  'DORM',              'หักค่าหอพัก',                    same('154101'), ''),
    (2250,  'UTILITIES',         'หักน้ำ/ไฟ/โทรศัพท์',             same('154101'), '★ บัญชีตรวจ'),
    (2310,  'TOOLS',             'หักค่าเครื่องมือ',               same('710006'), ''),
    (2260,  'UNIFORM_DED',       'หักค่าเครื่องแบบ',               same('710006'), ''),
    (2342,  'PER_DIEM_DED',      'หักเบี้ยเลี้ยง (จ่ายล่วงหน้า)', same('152103'), ''),
    (2340,  'DED_OTHER',         'หักอื่น ๆ',                      same('154101'), '★ บัญชีตรวจ (BPlus "หักอื่นๆ" 7.3 แสน/20 เดือน)'),
]
SSO_EMP = (8, 'SSO_EMPLOYER', 'สมทบประกันสังคม (นายจ้าง)',
           {'fac': '511012', 'off': '621012', 'exe': '621012'}, '232010')
# รหัส BPlus ที่รู้จักแต่ไม่นำเข้า (สถิติวันลา ยอด 0 / ยอดสรุปที่ใช้ตรวจทาน)
BPLUS_SKIP = {
    15: 'NET',   # เงินที่พนักงานได้รับ -> ใช้เทียบ NET ในชีต Control
    29: 'INFO',  # ภาษีที่โปรแกรมคำนวณได้ (ไม่ใช่ยอดหัก)
    2123: 'STAT', 2160: 'STAT', 2161: 'STAT', 2162: 'STAT', 2190: 'STAT',
    2171: 'STAT', 2122: 'STAT', 2140: 'STAT', 10036: 'STAT', 2124: 'STAT', 2121: 'STAT',
}
STRUCT = {'fac': ('structure_factory', 'structure_type_factory', 'เงินเดือน - โรงงาน (Legacy Import)',
                  'พนักงานโรงงาน (Legacy Import)'),
          'off': ('structure_office', 'structure_type_office', 'เงินเดือน - สำนักงาน (Legacy Import)',
                  'พนักงานสำนักงาน (Legacy Import)'),
          'exe': ('structure_executive', 'structure_type_executive', 'เงินเดือน - ผู้บริหาร (Legacy Import)',
                  'ผู้บริหาร (Legacy Import)')}
# input type ที่โมดูลอื่นเป็นเจ้าของ (ไม่สร้างซ้ำ, rule อ้างด้วย python แทน ref)
FOREIGN_TYPES = {'LOAN_INT'}


def type_xmlid(code):
    return EXISTING_TYPES.get(code, 'input_type_' + code.lower())


def rule_xmlid(g, code):
    return f'rule_{g}_{code.lower()}'


# ---------------- XML ----------------
L = ['<?xml version="1.0" encoding="utf-8"?>', '<odoo>',
     '    <!-- v4: generated 1 รหัส Business Plus = 1 input type (8 ก.ย. 2026) -->',
     '    <!-- อย่าแก้มือ - แก้ที่ tools/gen_payroll_config.py แล้ว generate ใหม่ -->',
     '    <!-- noupdate: record เดิมไม่ถูกทับตอน -u -> ชื่อ/ลำดับ/บัญชี ให้ wire_payroll_accounts_shell.py จัดการ -->',
     '    <data noupdate="1">']

all_items = [(c, n) for _, c, n, _, _ in EARNINGS] + [(c, n) for _, c, n, _, _ in DEDUCTIONS] + [(SSO_EMP[1], SSO_EMP[2])]
for code, name in all_items:
    if code in EXISTING_TYPES or code in FOREIGN_TYPES:
        continue
    L.append(f'''        <record id="{type_xmlid(code)}" model="hr.payslip.input.type">
            <field name="name">{name}</field>
            <field name="code">{code}</field>
            <field name="country_id" eval="False"/>
        </record>''')

for g in G:
    st_id, sty_id, st_name, sty_name = STRUCT[g]
    L.append(f'''        <record id="{sty_id}" model="hr.payroll.structure.type">
            <field name="name">{sty_name}</field>
            <field name="country_id" eval="False"/>
        </record>''')
    avail = [type_xmlid(c) for _, c, _, _, _ in EARNINGS + DEDUCTIONS if c not in FOREIGN_TYPES]
    avail.append(type_xmlid(SSO_EMP[1]))
    refs = ", ".join(f"ref('{x}')" for x in avail)
    L.append(f'''        <record id="{st_id}" model="hr.payroll.structure">
            <field name="name">{st_name}</field>
            <field name="type_id" ref="{sty_id}"/>
            <field name="country_id" eval="False"/>
            <field name="use_worked_day_lines" eval="False"/>
            <field name="rule_ids" eval="[(5, 0, 0)]"/>
            <field name="input_line_type_ids" eval="[(6, 0, [{refs}])]"/>
        </record>''')

    seq = 0
    for _, code, name, acc, _ in EARNINGS:
        seq += 2
        cat = 'BASIC' if code == 'BASIC' else 'ALW'
        L.append(f'''        <record id="{rule_xmlid(g, code)}" model="hr.salary.rule">
            <field name="struct_id" ref="{st_id}"/>
            <field name="category_id" ref="hr_payroll.{cat}"/>
            <field name="name">{name}</field>
            <field name="code">{code}</field>
            <field name="sequence">{1 if code == 'BASIC' else seq}</field>
            <field name="condition_select">input</field>
            <field name="condition_other_input_id" ref="{type_xmlid(code)}"/>
            <field name="amount_select">input</field>
            <field name="amount_other_input_id" ref="{type_xmlid(code)}"/>
        </record>''')
    L.append(f'''        <record id="rule_{g}_gross" model="hr.salary.rule">
            <field name="struct_id" ref="{st_id}"/>
            <field name="category_id" ref="hr_payroll.GROSS"/>
            <field name="name">รวมรายได้</field>
            <field name="code">GROSS</field>
            <field name="sequence">100</field>
            <field name="condition_select">none</field>
            <field name="amount_select">code</field>
            <field name="amount_python_compute">result = categories['BASIC'] + categories['ALW']</field>
        </record>''')
    seq = 100
    for _, code, name, acc, _ in DEDUCTIONS:
        seq += 2
        if code in FOREIGN_TYPES:
            cond = f'''            <field name="condition_select">python</field>
            <field name="condition_python">result = '{code}' in inputs</field>'''
        else:
            cond = f'''            <field name="condition_select">input</field>
            <field name="condition_other_input_id" ref="{type_xmlid(code)}"/>'''
        L.append(f'''        <record id="{rule_xmlid(g, code)}" model="hr.salary.rule">
            <field name="struct_id" ref="{st_id}"/>
            <field name="category_id" ref="hr_payroll.DED"/>
            <field name="name">{name}</field>
            <field name="code">{code}</field>
            <field name="sequence">{seq}</field>
{cond}
            <field name="amount_select">code</field>
            <field name="amount_python_compute">result = -inputs['{code}'].amount</field>
        </record>''')
    L.append(f'''        <record id="rule_{g}_sso_employer" model="hr.salary.rule">
            <field name="struct_id" ref="{st_id}"/>
            <field name="category_id" ref="hr_payroll.COMP"/>
            <field name="name">{SSO_EMP[2]}</field>
            <field name="code">SSO_EMPLOYER</field>
            <field name="sequence">190</field>
            <field name="appears_on_payslip" eval="False"/>
            <field name="condition_select">input</field>
            <field name="condition_other_input_id" ref="{type_xmlid('SSO_EMPLOYER')}"/>
            <field name="amount_select">input</field>
            <field name="amount_other_input_id" ref="{type_xmlid('SSO_EMPLOYER')}"/>
        </record>''')
    L.append(f'''        <record id="rule_{g}_net" model="hr.salary.rule">
            <field name="struct_id" ref="{st_id}"/>
            <field name="category_id" ref="hr_payroll.NET"/>
            <field name="name">เงินได้สุทธิ</field>
            <field name="code">NET</field>
            <field name="sequence">200</field>
            <field name="appears_on_employee_cost_dashboard" eval="True"/>
            <field name="condition_select">none</field>
            <field name="amount_select">code</field>
            <field name="amount_python_compute">result = categories['BASIC'] + categories['ALW'] + categories['DED']</field>
        </record>''')
    L.append(f'''        <record id="{sty_id}" model="hr.payroll.structure.type">
            <field name="default_struct_id" ref="{st_id}"/>
        </record>''')

L += ['    </data>', '</odoo>']
with open(XML_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L) + '\n')

# ---------------- wiring shell script ----------------
# xmlid -> (name, code, sequence, debit, credit)  ครอบทุก rule (record noupdate ต้องเขียนทับผ่าน shell)
wire = {}
for g in G:
    seq = 0
    for _, code, name, acc, _ in EARNINGS:
        seq += 2
        wire[rule_xmlid(g, code)] = (name, code, 1 if code == 'BASIC' else seq, acc[g], None)
    wire[f'rule_{g}_gross'] = ('รวมรายได้', 'GROSS', 100, None, None)
    seq = 100
    for _, code, name, acc, _ in DEDUCTIONS:
        seq += 2
        wire[rule_xmlid(g, code)] = (name, code, seq, acc[g], None)   # ยอดลบ: ช่อง debit = Cr
    wire[f'rule_{g}_sso_employer'] = (SSO_EMP[2], 'SSO_EMPLOYER', 190, SSO_EMP[3][g], SSO_EMP[4])
    wire[f'rule_{g}_net'] = ('เงินได้สุทธิ', 'NET', 200, None, '232001')
type_names = {type_xmlid(c): n for c, n in all_items if c not in FOREIGN_TYPES}
struct_types = {STRUCT[g][0]: sorted(type_names) for g in G}

W = ['# -*- coding: utf-8 -*-',
     '"""ผูกบัญชี Dr/Cr + ชื่อ/รหัส/ลำดับ rule + journal + ตั้งค่าบริษัท (generated - อย่าแก้มือ) รันผ่าน:',
     '    PYTHONUTF8=1 python odoo-bin shell -c odoo.conf -d <DB> --no-http < custom_addons/import_payslip_inputs/tools/wire_payroll_accounts_shell.py',
     'ต้องรันทุกครั้งหลัง restore DB และหลัง -u โมดูล (record ใน XML เป็น noupdate)"""',
     'MAP = ' + repr(wire),
     'TYPE_NAMES = ' + repr(type_names),
     'STRUCT_TYPES = ' + repr(struct_types),
     'RETIRED_TYPES = ' + repr(RETIRED_TYPE_XMLIDS),
     '''
Account = env['account.account']
def acc(code):
    a = Account.with_company(1).search([('code', '=', code)], limit=1)
    if not a:
        raise Exception('ไม่พบบัญชี ' + code)
    return a
def xref(xmlid):
    return env.ref('import_payslip_inputs.' + xmlid, raise_if_not_found=False)

# 1) input types: ชื่อให้ตรง generator + เปิดใช้ (บางตัวเคยถูก archive)
for xmlid, name in TYPE_NAMES.items():
    t = xref(xmlid)
    if not t:
        print('!! ไม่พบ input type', xmlid, '(ต้อง -u โมดูลก่อน)')
        continue
    t.write({'name': name, 'active': True})
for xmlid in RETIRED_TYPES:
    t = xref(xmlid)
    if t and t.active:
        t.active = False
        print('archive input type:', t.code)

# 2) rules: ชื่อ/รหัส/ลำดับ/บัญชี
wired = missing = 0
for xmlid, (name, code, seq, dr, cr) in MAP.items():
    rule = xref(xmlid)
    if not rule:
        print('!! ไม่พบ rule', xmlid)
        missing += 1
        continue
    rule.write({'name': name, 'code': code, 'sequence': seq, 'active': True,
                'account_debit': acc(dr).id if dr else False,
                'account_credit': acc(cr).id if cr else False})
    wired += 1
print(f'ผูกบัญชีแล้ว {wired} rules | หาไม่เจอ {missing}')

# 3) structures: input types ที่ให้เลือกในสลิป + journal + archive rule ที่ไม่อยู่ในตารางแล้ว
J = env['account.journal']
journal = J.search([('code', '=', 'PAYR')], limit=1)
if not journal:
    journal = J.create({'name': 'สมุดรายวันเงินเดือน', 'code': 'PAYR', 'type': 'general',
                        'default_account_id': acc('232001').id})
    print('สร้าง journal:', journal.name)
known_rule_ids = set()
for xmlid in MAP:
    r = xref(xmlid)
    if r:
        known_rule_ids.add(r.id)
structs = []
for st_xmlid, type_xmlids in STRUCT_TYPES.items():
    s = xref(st_xmlid)
    if not s:
        print('!! ไม่พบ structure', st_xmlid)
        continue
    structs.append(s)
    types = env['hr.payslip.input.type'].browse([xref(x).id for x in type_xmlids if xref(x)])
    s.write({'journal_id': journal.id, 'input_line_type_ids': [(6, 0, types.ids)]})
    stale = s.rule_ids.filtered(lambda r: r.id not in known_rule_ids and r.active)
    if stale:
        stale.active = False
        print(f'{s.name}: archive rule เก่าที่ไม่อยู่ในตาราง: {stale.mapped("code")}')
print('ตั้ง journal + input types ให้', len(structs), 'structures')

# 4) ใบสำคัญรวมทั้งงวด (ยอดรวมรายบัญชี ไม่โชว์รายคนใน GL)
env.company.batch_payroll_move_lines = True
print('batch_payroll_move_lines = True')

# 5) ปิดของเก่า (v2 structure เดี่ยว)
for xmlid in ('structure_legacy_import',):
    r = xref(xmlid)
    if r and r.active:
        r.active = False
        print('archive structure เก่า:', r.name)

env.cr.commit()
print('=== COMMITTED ===')
for s in structs:
    active_rules = s.rule_ids.filtered('active')
    no_acc = active_rules.filtered(lambda r: not r.account_debit and not r.account_credit and r.code != 'GROSS')
    print(f'{s.name}: rules {len(active_rules)} | ยังไม่ผูกบัญชี (ไม่นับ GROSS): {no_acc.mapped("code")}')
''']
with open(WIRE_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(W))

# ---------------- bplus_map.json (ให้ bplus_extract.py) ----------------
bmap = {'import': {}, 'skip': {str(k): v for k, v in BPLUS_SKIP.items()}}
for bp, code, name, _, _ in EARNINGS:
    if bp is not None:
        bmap['import'][str(bp)] = {'code': code, 'name': name, 'kind': 'earning'}
for bp, code, name, _, _ in DEDUCTIONS:
    if bp is not None:
        bmap['import'][str(bp)] = {'code': code, 'name': name, 'kind': 'deduction'}
bmap['import'][str(SSO_EMP[0])] = {'code': SSO_EMP[1], 'name': SSO_EMP[2], 'kind': 'company'}
# เงินกู้: รู้จักรหัสแต่ไม่ import (โมดูล custom_hr_loan เป็นเจ้าของ) -> ไปโผล่ในชีต Control แทน
bmap['import']['2320']['kind'] = 'loan'
with open(MAP_OUT, 'w', encoding='utf-8') as f:
    json.dump(bmap, f, ensure_ascii=False, indent=1)

# ---------------- doc ----------------
D = ['# ตารางแม็ปรหัส Business Plus → Odoo (1 รหัส = 1 บรรทัดสลิป)', '',
     'สร้างโดย `tools/gen_payroll_config.py` (8 ก.ย. 2026) — **บัญชีของรหัสใหม่ใช้ชุดของกลุ่มเดียวกันที่ยืนยันไว้ 6 ส.ค. 2026 ไปก่อน** '
     'แถวที่มี ★ คือจุดที่ขอให้บัญชีตรวจ/เลือกบัญชีใหม่ (แก้ได้ใน Payroll › Configuration › Salary Rules ไม่ต้องแก้โค้ด)', '',
     'ใบสำคัญ (JE) รวมยอดตามบัญชี ดังนั้น rule หลายตัวที่ชี้บัญชีเดียวกัน (เช่น OT 4 อัตรา) จะออกเป็นบรรทัดเดียวในสมุดรายวัน', '',
     '## รายได้ (ยอดบวก → Dr บัญชีในตาราง)', '',
     '| BPlus | Odoo code | ชื่อบนสลิป | โรงงาน | สำนักงาน | ผู้บริหาร | หมายเหตุ |', '|---|---|---|---|---|---|---|']
for bp, code, name, acc, note in EARNINGS:
    D.append(f"| {bp or '-'} | {code} | {name} | {acc['fac']} | {acc['off']} | {acc['exe']} | {note} |")
D += ['', '## รายการหัก (ยอดลบ → Cr บัญชีในตาราง; ในระบบใส่ไว้ช่อง Debit Account ตามกลไก Odoo)', '',
      '| BPlus | Odoo code | ชื่อบนสลิป | โรงงาน | สำนักงาน | ผู้บริหาร | หมายเหตุ |', '|---|---|---|---|---|---|---|']
for bp, code, name, acc, note in DEDUCTIONS:
    D.append(f"| {bp or '-'} | {code} | {name} | {acc['fac']} | {acc['off']} | {acc['exe']} | {note} |")
D += ['', '## สมทบนายจ้าง (ไม่แสดงบนสลิป)', '',
      f"| {SSO_EMP[0]} | {SSO_EMP[1]} | {SSO_EMP[2]} | Dr {SSO_EMP[3]['fac']} / {SSO_EMP[3]['off']} / {SSO_EMP[3]['exe']} | Cr {SSO_EMP[4]} |",
      '', '## รหัส BPlus ที่รู้จักแต่ไม่นำเข้า', '',
      '| BPlus | เหตุผล |', '|---|---|']
reason = {'NET': 'เงินที่พนักงานได้รับ — ใช้เทียบยอดสุทธิในชีต Control', 'INFO': 'ภาษีที่โปรแกรมคำนวณได้ — ตัวเลขอ้างอิง ไม่ใช่ยอดหัก',
          'STAT': 'สถิติวันลา/มาสาย ยอดเงินเป็น 0 เสมอ'}
for k, v in BPLUS_SKIP.items():
    D.append(f'| {k} | {reason[v]} |')
D += ['| 2320 | หักเงินกู้ — โมดูลเงินกู้สวัสดิการ (custom_hr_loan) หักเอง; ยอด BPlus โผล่ในชีต Control ไว้เทียบ |', '',
      'รหัส BPlus อื่นที่มียอดเงิน ≠ 0 แต่ไม่อยู่ในตาราง → `bplus_extract.py` จะหยุดพร้อมรายการ ให้เพิ่มในตารางนี้ก่อน']
with open(DOC_OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(D) + '\n')

n_types = sum(1 for c, n in all_items if c not in EXISTING_TYPES and c not in FOREIGN_TYPES)
print(f"XML: input types ใหม่ {n_types} | rules รวม {len(wire)} | BPlus codes import {len(bmap['import'])} skip {len(bmap['skip'])}")
for p in (XML_OUT, WIRE_OUT, MAP_OUT, DOC_OUT):
    print('เขียน:', p)
