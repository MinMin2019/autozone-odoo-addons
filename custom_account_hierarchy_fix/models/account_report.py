# -*- coding: utf-8 -*-
"""แถวหัวกลุ่มในรายงาน (Hierarchy and Subtotals) ให้โชว์เลขบัญชีเต็ม

ของเดิม Odoo ใช้ display_name ของ account.group = "ช่วงเลข + ชื่อ"
(เช่น "51 ค่าเงินเดือนและผลตอบแทนทางตรง") ซึ่งเป็นเลขย่อของช่วง prefix
ไม่ใช่รหัสบัญชีจริง — เปลี่ยนเป็นเลขบัญชีเต็มของบัญชีหัวข้อในผังแม่
("510000 ค่าเงินเดือนและผลตอบแทนทางตรง") ให้อ่านคู่กับแถวลูกได้ตรง ๆ
ช่วงเลขเดิมยังอยู่ใน tooltip และหน้า Account Groups ไม่ถูกแตะ
"""

from odoo import models


class AccountReport(models.Model):
    _inherit = "account.report"

    def _create_hierarchy(self, lines, options):
        lines = super()._create_hierarchy(lines, options)
        Group = self.env["account.group"]
        for line in lines:
            parsed = self._parse_line_id(line.get("id"))
            if not parsed:
                continue
            dummy, model, res_id = parsed[-1]
            if model != "account.group" or not res_id:
                continue
            group = Group.browse(res_id)
            source = group.az_source_account_id
            if source.code:
                line["name"] = "%s %s" % (source.code, group.name)
                line["title_hover"] = group.display_name
        return lines
