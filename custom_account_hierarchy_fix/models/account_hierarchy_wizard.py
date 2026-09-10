from odoo import fields, models


class AccountHierarchyWizard(models.TransientModel):
    _inherit = "sh.account.hierarchy.wizard"

    def update_context(self):
        """ของเดิมสร้าง dict เสร็จแล้วลืม return → client action ได้ context
        ว่างเปล่า: Auto Unfold ไม่ทำงาน และ get_main_lines หา wizard ไม่เจอ
        ต้อง fallback ไปหยิบ wizard ตัวเก่าสุดของ user (ค่าที่เพิ่งเลือกถูกทิ้ง)
        — override ให้คืน context จริง พร้อม id ของ wizard ตัวที่กด Confirm"""
        self.ensure_one()
        return {
            "active_id": self.id,
            "wizard_id": self.id,
            "auto_unfold": self.auto_unfold or False,
            "start_date": fields.Date.to_string(self.start_date) or "",
            "end_date": fields.Date.to_string(self.end_date) or "",
            "target_moves": self.target_moves,
            "include_zero_amount_transaction": self.include_zero_amount_transaction,
            "hierarchy_based_on": self.hierarchy_based_on,
        }
