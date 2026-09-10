# v1.2.0: เลขที่เงินกู้เปลี่ยนจาก LN/<ค.ศ.>/0001 เป็น LC<พ.ศ.>/001 (รีเซ็ตทุกปี)
# ir.sequence อยู่ใน data noupdate=1 จึงต้องแก้ record เดิมในฐานที่ติดตั้งไปแล้วตรงนี้


def migrate(cr, version):
    cr.execute(
        "UPDATE ir_sequence SET prefix = NULL, padding = 3, use_date_range = true "
        "WHERE code = 'hr.employee.loan'"
    )
