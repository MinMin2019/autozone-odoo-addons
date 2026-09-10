# v1.3.0: amount_untaxed เปลี่ยนจากช่องกรอกเป็น computed จาก amount_entry
# — คัดลอกค่าเดิมเข้า amount_entry ก่อน ORM โหลด (กันข้อมูลเดิมโดนล้าง)


def migrate(cr, version):
    cr.execute(
        "ALTER TABLE petty_cash_clearing_line "
        "ADD COLUMN IF NOT EXISTS amount_entry numeric"
    )
    cr.execute(
        "UPDATE petty_cash_clearing_line "
        "SET amount_entry = amount_untaxed WHERE amount_entry IS NULL"
    )
