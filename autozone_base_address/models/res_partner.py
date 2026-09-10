from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def get_thai_state_display(self):
        """ชื่อจังหวัดพร้อม "จ." นำหน้า ยกเว้นกรุงเทพมหานคร (และที่อยู่ต่างประเทศ)"""
        self.ensure_one()
        state = (self.state_id.name or "").strip()
        if not state:
            return ""
        is_thai = not self.country_id or self.country_id.code == "TH"
        if is_thai and "กรุงเทพ" not in state:
            return "จ." + state
        return state

    def get_thai_address_lines(self):
        """ที่อยู่แบ่ง 2 บรรทัด: [street street2, city จ.state zip]

        สำหรับฟอร์มที่ layout บังคับแบ่งบรรทัด (dot-matrix, voucher)
        มาตรฐานการกรอกข้อมูล: city ต้องมี "อ." นำหน้า (กรุงเทพใช้ "เขต")
        ไม่ใช้ comma คั่น
        """
        self.ensure_one()
        line1 = " ".join(
            p.strip() for p in [self.street, self.street2] if p and p.strip()
        )
        parts = []
        if self.city and self.city.strip():
            parts.append(self.city.strip())
        state = self.get_thai_state_display()
        if state:
            parts.append(state)
        if self.zip and self.zip.strip():
            parts.append(self.zip.strip())
        return [line1, " ".join(parts)]

    def get_thai_branch_display(self):
        """ป้ายสาขาตามประกาศสรรพากร: "สำนักงานใหญ่" / "สาขาที่ 00001"

        อ่านจาก field `branch` ของ l10n_th_partner (OCA) — ถ้าไม่ได้ติดตั้ง
        หรือไม่ได้กรอก คืนสตริงว่าง; ค่าที่ไม่ใช่ตัวเลขคืนตามที่กรอกไว้
        """
        self.ensure_one()
        branch = (getattr(self, "branch", "") or "").strip()
        if not branch:
            return ""
        if branch == "00000":
            return "สำนักงานใหญ่"
        if branch.isdigit():
            return "สาขาที่ " + branch
        return branch

    def get_thai_vat_line(self):
        """เลขผู้เสียภาษี + ป้ายสาขา ในบรรทัดเดียว เช่น "0105555021215 สำนักงานใหญ่" """
        self.ensure_one()
        parts = [(self.vat or "").strip(), self.get_thai_branch_display()]
        return " ".join(p for p in parts if p)

    def get_thai_address(self):
        """ที่อยู่แบบไทยบรรทัดเดียว: street street2 city จ.state zip

        ที่อยู่ต่างประเทศ (country != TH) ต่อท้ายด้วยชื่อประเทศ และไม่เติม "จ."
        """
        self.ensure_one()
        parts = [line for line in self.get_thai_address_lines() if line]
        if self.country_id and self.country_id.code != "TH":
            parts.append(self.country_id.name)
        return " ".join(parts)
