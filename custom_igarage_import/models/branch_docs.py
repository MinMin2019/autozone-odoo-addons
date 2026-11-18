from odoo import fields, models


class BranchTransfer(models.Model):
    _inherit = "az.branch.transfer"

    igarage_do_ref = fields.Char("เลข DO iGarage", index=True, copy=False, readonly=True)


class BranchConsumption(models.Model):
    _inherit = "az.branch.consumption"

    import_ref = fields.Char("อ้างอิงการดึงข้อมูล", index=True, copy=False, readonly=True,
                             help="เช่น IGARAGE:ICR:2026-11 หรือ AUTOPART:ATP:2026-11 — กันดึงเดือนเดียวกันซ้ำ")
