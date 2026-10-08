# -*- coding: utf-8 -*-
"""นำเข้ายอดนับจากไฟล์ Excel ที่ Export ออกจากใบนับแล้วกรอกคอลัมน์ "ยอดตรวจนับ" กลับมา

จับคู่สินค้า: คอลัมน์ I (product id) → รหัสสินค้า (B) → ชื่อสินค้า (C)
แถวที่คอลัมน์ F (ยอดตรวจนับ) ว่าง = ยังไม่นับ ข้าม; คอลัมน์ H = หมายเหตุ
หัวตารางหาจากแถวที่ A = "ลำดับ" จึงรับไฟล์ที่ผู้ใช้แทรก/ลบแถวหัวกระดาษได้
"""
import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockCountImport(models.TransientModel):
    _name = "az.stock.count.import"
    _description = "นำเข้ายอดนับจาก Excel"

    count_id = fields.Many2one("az.stock.count", required=True, ondelete="cascade")
    file = fields.Binary("ไฟล์ Excel (.xlsx)", required=True)
    filename = fields.Char()
    overwrite = fields.Boolean(
        "ทับยอดที่คีย์ไว้แล้ว", default=True,
        help="ไม่ติ๊ก = รายการที่คีย์ในจอไปแล้วจะไม่ถูกแก้ด้วยค่าจากไฟล์",
    )
    result = fields.Text("ผลการนำเข้า", readonly=True)

    @api.model
    def _to_float(self, value):
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            raise UserError(_("ค่ายอดนับ '%s' ไม่ใช่ตัวเลข", value))

    def action_import(self):
        self.ensure_one()
        count = self.count_id
        count._check_state(("counting",), "นำเข้ายอดนับจาก Excel")
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise UserError(_("เซิร์ฟเวอร์ไม่มี openpyxl"))
        try:
            wb = load_workbook(io.BytesIO(base64.b64decode(self.file)), data_only=True, read_only=True)
        except Exception as e:
            raise UserError(_("เปิดไฟล์ไม่ได้ (ต้องเป็น .xlsx): %s", e))

        lines = count.line_ids
        by_id = {l.product_id.id: l for l in lines}
        by_code = {}
        by_name = {}
        for l in lines:
            if l.product_id.default_code:
                by_code.setdefault(l.product_id.default_code.strip(), l)
            by_name.setdefault((l.product_id.name or "").strip(), l)

        updated = skipped = unmatched = 0
        problems = []
        for ws in wb.worksheets:
            header_found = False
            for row in ws.iter_rows(values_only=True):
                cells = list(row) + [None] * (9 - len(row))
                a, b, c, _d, _e, f, _g, h, i = cells[:9]
                if not header_found:
                    if isinstance(a, str) and a.strip() == "ลำดับ":
                        header_found = True
                    continue
                if not (b or c or i):
                    continue  # แถวว่าง / หัวหมวด / ลายเซ็น
                if isinstance(a, str) and not b and not i:
                    continue  # หัวหมวด (merge A:H)
                line = None
                if i not in (None, ""):
                    try:
                        line = by_id.get(int(float(i)))
                    except (TypeError, ValueError):
                        line = None
                if not line and b not in (None, ""):
                    line = by_code.get(str(b).strip())
                if not line and c:
                    line = by_name.get(str(c).strip())
                if not line:
                    unmatched += 1
                    if len(problems) < 20:
                        problems.append("%s | %s" % (b or "", c or ""))
                    continue
                qty = self._to_float(f)
                if qty is None:
                    skipped += 1
                    continue
                if line.counted and not self.overwrite:
                    skipped += 1
                    continue
                vals = {"qty_counted": qty, "counted": True}
                if h not in (None, ""):
                    vals["note"] = str(h).strip()
                line.write(vals)
                updated += 1
            if header_found:
                break
            problems.append(_("ชีท '%s': ไม่พบหัวตาราง (แถวที่คอลัมน์ A = ลำดับ)", ws.title))

        summary = _("นำเข้าแล้ว %(u)d รายการ, ข้าม (ไม่ได้กรอก/ไม่ทับ) %(s)d, จับคู่สินค้าไม่ได้ %(x)d",
                    u=updated, s=skipped, x=unmatched)
        if problems:
            summary += "\n" + "\n".join(problems)
        count.message_post(body=_("นำเข้ายอดนับจากไฟล์ %(f)s: %(s)s", f=self.filename or "", s=summary))
        self.result = summary
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
