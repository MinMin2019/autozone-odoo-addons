from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError


class PaymentDuplicateWizard(models.TransientModel):
    _name = "payment.duplicate.wizard"
    _description = "Duplicate Payments with Journal Items"

    date = fields.Date(
        string="วันที่จ่าย / วันที่ลงบัญชีใหม่",
        required=True,
        default=fields.Date.context_today,
    )
    payment_ids = fields.Many2many(
        comodel_name="account.payment",
        string="Payment ต้นฉบับ",
        required=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "payment_ids" in fields_list and self.env.context.get("active_model") == "account.payment":
            res["payment_ids"] = [Command.set(self.env.context.get("active_ids", []))]
        return res

    def action_duplicate(self):
        self.ensure_one()

        no_move = self.payment_ids.filtered(lambda p: not p.move_id)
        if no_move:
            raise UserError(_(
                "รายการต่อไปนี้ไม่มี Journal Entry ให้คัดลอก กรุณาเอาออกก่อน:\n%s",
                "\n".join(no_move.mapped("display_name")),
            ))
        no_outstanding = self.payment_ids.filtered(lambda p: not p.outstanding_account_id)
        if no_outstanding:
            raise UserError(_(
                "สมุดรายวันของรายการต่อไปนี้ไม่มี Outstanding Account "
                "(ตั้งค่าที่ Journal > Payment Method ก่อน):\n%s",
                "\n".join(no_outstanding.mapped("display_name")),
            ))

        new_payments = self.env["account.payment"]
        for pay in self.payment_ids:
            new_pay = pay.copy({"date": self.date})
            new_pay._generate_journal_entry()
            new_move = new_pay.move_id
            if not new_move:
                raise UserError(_(
                    "สร้าง Journal Entry ให้ %s ไม่สำเร็จ",
                    pay.display_name,
                ))

            # แทนบรรทัดมาตรฐาน (ธนาคาร + เจ้าหนี้) ด้วยบรรทัดจริงจากเอกสารต้นฉบับ
            # ไม่คัดลอก tax_ids/tax grids — เอกสารจ่ายเงินเดือนไม่มีภาษีขาย/ซื้อ
            # และการคัดลอกจะทำให้ระบบสร้างบรรทัดภาษีซ้ำ
            line_commands = [Command.clear()]
            for line in pay.move_id.line_ids:
                line_commands.append(Command.create({
                    "name": line.name,
                    "account_id": line.account_id.id,
                    "partner_id": line.partner_id.id,
                    "currency_id": line.currency_id.id,
                    "amount_currency": line.amount_currency,
                    "debit": line.debit,
                    "credit": line.credit,
                    "analytic_distribution": line.analytic_distribution,
                    "date_maturity": self.date,
                }))
            new_move.write({
                "date": self.date,
                "line_ids": line_commands,
            })

            # คงสถานะ Draft ทั้ง payment และ entry ให้ผู้ใช้ตรวจ/แก้ยอดก่อนกด Confirm
            new_pay.state = "draft"
            new_move.message_post(body=_(
                "คัดลอกรายการบัญชีมาจาก %s",
                pay.move_id._get_html_link(),
            ))
            new_payments |= new_pay

        return {
            "type": "ir.actions.act_window",
            "name": _("Payment ที่คัดลอกแล้ว (ร่าง)"),
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("id", "in", new_payments.ids)],
        }
