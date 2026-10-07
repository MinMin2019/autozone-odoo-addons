# v1.3.0: เพิ่มวันที่ชำระที่งวดผ่อน (ใช้หาเดือนของงวดที่โปะล่วงหน้าในรายงานเงินกู้)
# งวดชำระเองเดิมไม่มีวันที่ — ถือว่าชำระตามกำหนดหัก จะได้ไม่ถูกนับเป็นโปะล่วงหน้า


def migrate(cr, version):
    cr.execute(
        "UPDATE hr_employee_loan_line SET date_paid = date_due "
        "WHERE manual_paid AND date_paid IS NULL"
    )
