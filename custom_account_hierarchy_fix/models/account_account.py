from odoo import api, models
from odoo.exceptions import ValidationError


class AccountAccount(models.Model):
    _inherit = "account.account"

    @api.constrains("sh_parent_id", "account_type")
    def _check_sh_parent_hierarchy(self):
        """กันข้อมูล Parent เสียซึ่งทำให้รายงาน hierarchy พัง:
        - ชี้ตัวเอง/วนลูป → บัญชีหายจากรายงานทั้งสาย และโค้ดรวมยอดของ
          sh_account_parent เป็น recursion ไม่มีตัวจบ (server ค้างตอนกดกาง)
        - parent ไม่ใช่ Type View → รายงานกางได้เฉพาะบัญชี View
          ลูกที่ผูกกับบัญชีธรรมดาจะไม่มีทางไต่ถึง (ข้อมูลหายเงียบ ๆ)
        """
        for account in self:
            if account.sh_parent_id == account:
                raise ValidationError(
                    f"{account.display_name} ตั้ง Parent Account เป็นตัวเองไม่ได้ "
                    f"(บัญชีจะหายจากรายงาน hierarchy ทั้งสาย)"
                )
            # เปลี่ยน type ของบัญชีแม่ที่มีลูกผูกอยู่ ออกจาก View → ลูกกลายเป็นกำพร้า
            if account.account_type != "view":
                child = self.search([("sh_parent_id", "=", account.id)], limit=1)
                if child:
                    raise ValidationError(
                        f"{account.display_name} ยังมีบัญชีลูกผูกอยู่ (เช่น {child.display_name}) "
                        f"— ต้องคง Type เป็น View หรือย้ายลูกออกก่อน"
                    )
            if not account.sh_parent_id:
                continue
            if account.sh_parent_id.account_type != "view":
                raise ValidationError(
                    f"Parent Account ต้องเป็นบัญชีประเภท View เท่านั้น — "
                    f"{account.sh_parent_id.display_name} ไม่ใช่ View "
                    f"(บัญชีลูกที่ผูกกับบัญชีธรรมดาจะไม่แสดงในรายงาน hierarchy)"
                )
            seen = account
            node = account.sh_parent_id
            while node:
                if node in seen:
                    raise ValidationError(
                        f"ตั้ง Parent Account แบบนี้ไม่ได้ — เกิดการชี้วนลูป: "
                        f"{account.display_name} → {account.sh_parent_id.display_name} "
                        f"ย้อนกลับมาหาตัวเองในสายบรรพบุรุษ"
                    )
                seen |= node
                node = node.sh_parent_id
