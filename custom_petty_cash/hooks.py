"""ตั้งค่าบัญชี/journal พื้นฐานของระบบเงินสดย่อยให้อัตโนมัติ

รันตอนติดตั้งโมดูล (post_init_hook) และตอนอัพเกรด (migrations)
idempotent — มีอยู่แล้วข้าม รันซ้ำได้ทุกฐาน

ประวัติดีไซน์: v1.5.0 เคยสร้างบัญชีพักแยก 111007 แต่ฝ่ายบัญชีสรุป (27 ส.ค. 69)
ให้กลับไปใช้ 111001 บัญชีพักเงินจ่ายตัวเดิมร่วมกับใบสำคัญจ่าย PVC
"""


def _setup_petty_cash_outstanding(env):
    company = env.ref("base.main_company")

    # บัญชีพักเงินจ่าย = 111001 (ตัวเดียวกับ PVC ตามที่ฝ่ายบัญชีกำหนด)
    # ปกติมีอยู่แล้วทุกฐาน — สร้างให้เฉพาะฐานเปล่าจริง ๆ และไม่แตะ reconcile ของเดิม
    Account = env["account.account"].with_company(company)
    outstanding = Account.search([("code", "=", "111001")], limit=1)
    if not outstanding:
        outstanding = Account.create({
            "code": "111001",
            "name": "Cash On Hand",
            "account_type": "asset_cash",
        })

    # purchase journal กลางสำหรับ vendor bill จากใบเคลียร์ (ทุกกองใช้ร่วมกัน)
    Journal = env["account.journal"].with_company(company)
    if not Journal.search([("code", "=", "PCB"), ("type", "=", "purchase")], limit=1):
        Journal.create({
            "name": "ตั้งหนี้เงินสดย่อย",
            "code": "PCB",
            "type": "purchase",
            "company_id": company.id,
        })

    return outstanding


def post_init_hook(env):
    _setup_petty_cash_outstanding(env)
