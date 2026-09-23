# -*- coding: utf-8 -*-
"""กระทบยอดสต็อกกับบัญชี (Inventory to GL Reconciliation)

ส่วน A (section = valuation) — ต่อบัญชีสินค้าคงเหลือ 141xxx
  physical  = Σ (จำนวนคงเหลือ ณ วันที่ จาก stock.move.line ใน internal + transit ของบริษัท) x standard_price ปัจจุบัน   [เฉพาะสินค้าเก็บสต็อก]
  svl       = Σ stock.valuation.layer.value ที่ create_date <= วันที่
  gl        = Σ account.move.line.balance (posted, date <= วันที่) ของบัญชีนั้น
  gl - svl  = je_no_svl (บรรทัด GL ที่ JE ไม่ได้มาจาก SVL)
              - svl_no_je (SVL ที่ไม่มี JE: หมวด Manual / สินค้าไม่เก็บสต็อก)
              + linked_diff (ผูกกันแต่ยอดไม่เท่า เช่น JE คนละงวดกับ SVL = cut-off)
  svl - physical = สินค้าผี (SVL ของสินค้าที่ไม่มีของ) + ต้นทุนใน SVL ต่างจาก standard ปัจจุบัน

ส่วน B (section = suspense) — บัญชีพักสินค้าขาเข้า / ขาออก (stock input / output ของหมวด)
  gl ณ วันที่, แยกตามสมุดรายวัน + มาจาก SVL (ใบรับ/ใบส่ง) หรือไม่, ยอดที่ยังไม่จับคู่
"""
import base64
import io
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def thai_date(d):
    if not d:
        return ""
    return "%02d/%02d/%d" % (d.day, d.month, d.year + 543)


class StockGlReconWizard(models.TransientModel):
    _name = "stock.gl.recon.wizard"
    _description = "กระทบยอดสต็อกกับบัญชี"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    date_to = fields.Date("ณ วันที่", required=True, default=fields.Date.context_today)
    extra_account_ids = fields.Many2many(
        "account.account", string="บัญชีสินค้าเพิ่มเติม",
        help="บัญชีสินค้าคงเหลือที่ไม่ได้ผูกกับหมวดสินค้าใด แต่ต้องการกระทบยอดด้วย",
    )
    line_ids = fields.One2many("stock.gl.recon.line", "wizard_id")
    line_count = fields.Integer(compute="_compute_line_count")

    @api.model
    def default_get(self, fields_list):
        """ค่าเริ่มต้นบัญชีเพิ่มเติม = บัญชีที่รหัสขึ้นต้นเหมือนบัญชีสินค้าของหมวด (เช่น 141xxx)
        แต่ไม่ได้ผูกกับหมวดใด และไม่ใช่บัญชีพักขาเข้า/ขาออก — ผู้ใช้ถอดออกได้"""
        res = super().default_get(fields_list)
        if "extra_account_ids" in fields_list and not res.get("extra_account_ids"):
            company = self.env.company
            Categ = self.env["product.category"].with_company(company).with_context(active_test=False)
            mapped, prefixes = set(), set()
            for c in Categ.search([]):
                for a in (c.property_stock_valuation_account_id, c.property_stock_account_input_categ_id,
                          c.property_stock_account_output_categ_id):
                    if a:
                        mapped.add(a.id)
                if c.property_stock_valuation_account_id and c.property_stock_valuation_account_id.code:
                    prefixes.add(c.property_stock_valuation_account_id.code[:3])
            extra = self.env["account.account"]
            for pre in prefixes:
                extra |= self.env["account.account"].with_company(company).search(
                    [("code", "=like", pre + "%"), ("company_ids", "in", company.id),
                     ("account_type", "=", "asset_current"), ("id", "not in", list(mapped))]
                )
            if extra:
                res["extra_account_ids"] = [(6, 0, extra.ids)]
        return res

    @api.depends("date_to")
    def _compute_name(self):
        for w in self:
            w.name = "กระทบยอดสต็อกกับบัญชี ณ %s" % thai_date(w.date_to)

    @api.depends("line_ids")
    def _compute_line_count(self):
        for w in self:
            w.line_count = len(w.line_ids)

    def _utc_end(self):
        tz = pytz.timezone(self.env.user.tz or "Asia/Bangkok")
        local = tz.localize(datetime.combine(self.date_to + timedelta(days=1), time.min))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    # คำนวณ
    # ------------------------------------------------------------------
    def action_compute(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.env.flush_all()
        cid = self.company_id.id
        end = self._utc_end()
        cr = self.env.cr

        # ---------- 1. หมวดสินค้า → บัญชี ----------
        Categ = self.env["product.category"].with_company(self.company_id).with_context(active_test=False)
        categs = Categ.search([])
        val_acc_by_categ, categ_manual = {}, {}
        input_accs, output_accs = set(), set()
        for c in categs:
            val_acc_by_categ[c.id] = c.property_stock_valuation_account_id.id or False
            categ_manual[c.id] = c.property_valuation != "real_time"
            if c.property_stock_account_input_categ_id:
                input_accs.add(c.property_stock_account_input_categ_id.id)
            if c.property_stock_account_output_categ_id:
                output_accs.add(c.property_stock_account_output_categ_id.id)
        val_accs = {a for a in val_acc_by_categ.values() if a} | set(self.extra_account_ids.ids)

        # ---------- 2. สินค้า ----------
        cr.execute(
            """SELECT pp.id, pt.categ_id, pt.is_storable, pt.type
                 FROM product_product pp JOIN product_template pt ON pt.id = pp.product_tmpl_id"""
        )
        prod_info = {r[0]: {"categ": r[1], "storable": bool(r[2]), "type": r[3]} for r in cr.fetchall()}
        Product = self.env["product.product"].with_context(active_test=False).with_company(self.company_id)

        # ---------- 3. SVL ณ วันที่ ต่อสินค้า ----------
        cr.execute(
            """SELECT product_id,
                      COALESCE(SUM(value), 0),
                      COALESCE(SUM(CASE WHEN account_move_id IS NULL THEN value ELSE 0 END), 0),
                      COALESCE(SUM(quantity), 0),
                      COUNT(*)
                 FROM stock_valuation_layer
                WHERE company_id = %s AND create_date < %s
             GROUP BY product_id""",
            (cid, end),
        )
        svl = {r[0]: {"value": r[1], "no_je": r[2], "qty": r[3], "count": r[4]} for r in cr.fetchall()}

        # ---------- 4. จำนวนคงเหลือ ณ วันที่ ต่อสินค้า (ตำแหน่งที่ตีมูลค่า) ----------
        # ตำแหน่งที่ "ของยังเป็นสต็อกบริษัท" = internal + transit ที่มี company
        # (ตาม stock.location._should_be_valued ของ Odoo) — ของที่ค้างในคลังพัก
        # ระหว่างส่ง/รับของ Flow B (TOUT→TIN) ยังอยู่ใน SVL จึงต้องนับด้วย
        # ไม่งั้นโชว์เป็น "สินค้าผี" หลอก (บั๊กที่เจอ 23 ก.ย. 2026)
        cr.execute(
            """SELECT x.product_id,
                      COALESCE(SUM(CASE WHEN x.dst_valued THEN x.qty ELSE 0 END), 0)
                    - COALESCE(SUM(CASE WHEN x.src_valued THEN x.qty ELSE 0 END), 0)
                 FROM (
                    SELECT ml.product_id, ml.quantity_product_uom AS qty,
                           (ls.usage = 'internal'
                            OR (ls.usage = 'transit' AND ls.company_id IS NOT NULL)) AS src_valued,
                           (ld.usage = 'internal'
                            OR (ld.usage = 'transit' AND ld.company_id IS NOT NULL)) AS dst_valued
                      FROM stock_move_line ml
                      JOIN stock_move m ON m.id = ml.move_id
                      JOIN stock_location ls ON ls.id = ml.location_id
                      JOIN stock_location ld ON ld.id = ml.location_dest_id
                     WHERE ml.state = 'done' AND m.company_id = %s AND ml.date < %s
                 ) x
                WHERE x.src_valued <> x.dst_valued
             GROUP BY x.product_id""",
            (cid, end),
        )
        onhand = {r[0]: r[1] for r in cr.fetchall()}

        # ต้นทุนปัจจุบัน
        pids = set(svl) | {p for p, q in onhand.items() if abs(q) > 1e-6}
        std_cost = {}
        for p in Product.browse(list(pids)):
            std_cost[p.id] = p.standard_price or 0.0

        # ---------- 5. GL ต่อบัญชี ----------
        all_accs = list(val_accs | input_accs | output_accs)
        gl_total, gl_linked, gl_by_journal = {}, {}, defaultdict(dict)
        gl_unrec = {}
        if all_accs:
            # JE ที่มาจาก SVL
            cr.execute(
                """SELECT l.account_id, l.journal_id,
                          (l.move_id IN (SELECT account_move_id FROM stock_valuation_layer
                                          WHERE account_move_id IS NOT NULL)) AS linked,
                          COALESCE(SUM(l.balance), 0), COALESCE(SUM(l.debit), 0), COALESCE(SUM(l.credit), 0),
                          COUNT(*),
                          COALESCE(SUM(CASE WHEN l.full_reconcile_id IS NULL THEN l.balance ELSE 0 END), 0)
                     FROM account_move_line l
                    WHERE l.company_id = %s AND l.parent_state = 'posted'
                      AND l.date <= %s AND l.account_id = ANY(%s)
                 GROUP BY l.account_id, l.journal_id, linked""",
                (cid, self.date_to, all_accs),
            )
            for acc, jrn, linked, bal, deb, cre, cnt, unrec in cr.fetchall():
                gl_total[acc] = gl_total.get(acc, 0.0) + bal
                if linked:
                    gl_linked[acc] = gl_linked.get(acc, 0.0) + bal
                gl_unrec[acc] = gl_unrec.get(acc, 0.0) + unrec
                gl_by_journal[acc][(jrn, bool(linked))] = (bal, deb, cre, cnt, unrec)

        # ---------- 6. รวมต่อบัญชีสินค้าคงเหลือ ----------
        per_acc = defaultdict(lambda: {"physical": 0.0, "svl": 0.0, "svl_no_je": 0.0,
                                       "svl_non_storable": 0.0, "products": {}})
        for pid in pids:
            info = prod_info.get(pid)
            if not info:
                continue
            acc = val_acc_by_categ.get(info["categ"], False)
            qty = onhand.get(pid, 0.0)
            cost = std_cost.get(pid, 0.0)
            phys = qty * cost if info["storable"] else 0.0
            s = svl.get(pid, {"value": 0.0, "no_je": 0.0, "qty": 0.0, "count": 0})
            if abs(qty) < 1e-6 and abs(s["value"]) < 0.005 and abs(s["qty"]) < 1e-6:
                continue
            d = per_acc[acc]
            d["physical"] += phys
            d["svl"] += s["value"]
            d["svl_no_je"] += s["no_je"]
            if not info["storable"]:
                d["svl_non_storable"] += s["value"]
            d["products"][pid] = {
                "qty": qty, "cost": cost, "physical": phys, "svl": s["value"],
                "svl_qty": s["qty"], "svl_no_je": s["no_je"], "storable": info["storable"],
                "categ": info["categ"], "manual": categ_manual.get(info["categ"], True),
            }
        for acc in val_accs:
            per_acc.setdefault(acc, {"physical": 0.0, "svl": 0.0, "svl_no_je": 0.0,
                                     "svl_non_storable": 0.0, "products": {}})

        Line = self.env["stock.gl.recon.line"]
        Detail = self.env["stock.gl.recon.detail"]
        Account = self.env["account.account"].with_company(self.company_id)
        Journal = self.env["account.journal"]
        acc_rec = {a.id: a for a in Account.browse([a for a in per_acc if a] + list(input_accs | output_accs))}
        line_vals, detail_vals = [], []
        seq = 0

        def acc_fields(acc):
            a = acc_rec.get(acc)
            return {
                "account_id": acc or False,
                "account_code": a.code if a else "",
                "account_name": a.name if a else "ไม่ได้ผูกบัญชี (หมวดไม่มีบัญชีสินค้า)",
            }

        mapped_val_accs = {a for a in val_acc_by_categ.values() if a}
        for acc in sorted(per_acc, key=lambda a: (a is False, acc_rec[a].code if a and a in acc_rec else "")):
            d = per_acc[acc]
            gl = gl_total.get(acc, 0.0) if acc else 0.0
            if acc and acc not in mapped_val_accs and not d["products"] and abs(gl) < 0.005:
                continue  # บัญชีเพิ่มเติมที่ไม่มีอะไรเลย ไม่ต้องแสดง
            linked = gl_linked.get(acc, 0.0) if acc else 0.0
            je_no_svl = gl - linked
            svl_with_je = d["svl"] - d["svl_no_je"]
            linked_diff = linked - svl_with_je
            seq += 10
            v = {
                "wizard_id": self.id, "section": "valuation", "sequence": seq,
                "physical_value": d["physical"], "svl_value": d["svl"], "gl_value": gl,
                "diff_gl_svl": gl - d["svl"], "svl_no_je": d["svl_no_je"],
                "svl_non_storable": d["svl_non_storable"], "je_no_svl": je_no_svl,
                "linked_diff": linked_diff, "diff_svl_phys": d["svl"] - d["physical"],
                "gl_unreconciled": 0.0, "product_count": len(d["products"]),
            }
            v.update(acc_fields(acc))
            line_vals.append(v)
            dets = []
            for pid, p in sorted(d["products"].items(), key=lambda kv: -abs(kv[1]["svl"] - kv[1]["physical"])):
                dets.append({
                    "kind": "product", "product_id": pid, "categ_id": p["categ"],
                    "qty": p["qty"], "svl_qty": p["svl_qty"], "unit_cost": p["cost"],
                    "physical_value": p["physical"], "svl_value": p["svl"],
                    "svl_no_je": p["svl_no_je"], "diff_value": p["svl"] - p["physical"],
                    "is_storable": p["storable"], "is_manual": p["manual"],
                })
            if acc:
                for (jrn, lk), (bal, deb, cre, cnt, unrec) in sorted(gl_by_journal.get(acc, {}).items(), key=lambda kv: -abs(kv[1][0])):
                    dets.append({
                        "kind": "journal", "journal_id": jrn, "linked": lk,
                        "debit": deb, "credit": cre, "balance": bal, "line_count": cnt,
                        "unreconciled": unrec,
                    })
            detail_vals.append(dets)

        # รวมส่วน A
        tot = {k: sum(v[k] for v in line_vals) for k in
               ["physical_value", "svl_value", "gl_value", "diff_gl_svl", "svl_no_je",
                "svl_non_storable", "je_no_svl", "linked_diff", "diff_svl_phys"]}
        seq += 10
        tot.update({"wizard_id": self.id, "section": "valuation", "sequence": seq, "is_total": True,
                    "account_code": "", "account_name": "รวมบัญชีสินค้าคงเหลือ",
                    "product_count": sum(v["product_count"] for v in line_vals)})
        line_vals.append(tot)
        detail_vals.append([])

        # ---------- 7. ส่วน B บัญชีพัก ----------
        for kind, accs in (("input", input_accs), ("output", output_accs)):
            for acc in sorted(accs, key=lambda a: acc_rec[a].code if a in acc_rec else ""):
                gl = gl_total.get(acc, 0.0)
                linked = gl_linked.get(acc, 0.0)
                seq += 10
                v = {
                    "wizard_id": self.id, "section": "suspense", "sequence": seq,
                    "suspense_kind": kind, "gl_value": gl, "gl_linked": linked,
                    "je_no_svl": gl - linked, "gl_unreconciled": gl_unrec.get(acc, 0.0),
                    "is_reconcilable": acc_rec[acc].reconcile if acc in acc_rec else False,
                }
                v.update(acc_fields(acc))
                line_vals.append(v)
                dets = []
                for (jrn, lk), (bal, deb, cre, cnt, unrec) in sorted(gl_by_journal.get(acc, {}).items(), key=lambda kv: -abs(kv[1][0])):
                    dets.append({
                        "kind": "journal", "journal_id": jrn, "linked": lk,
                        "debit": deb, "credit": cre, "balance": bal, "line_count": cnt,
                        "unreconciled": unrec,
                    })
                detail_vals.append(dets)

        lines = Line.create(line_vals)
        flat = []
        for line, dets in zip(lines, detail_vals):
            for i, dv in enumerate(dets):
                dv["line_id"] = line.id
                dv["sequence"] = i
                flat.append(dv)
        if flat:
            Detail.create(flat)
        _logger.info("stock gl recon: %d lines / %d details", len(lines), len(flat))
        return lines

    def _ensure_lines(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_compute()
        return self.line_ids

    # ------------------------------------------------------------------
    # ปุ่ม
    # ------------------------------------------------------------------
    def action_view(self):
        self.ensure_one()
        self.action_compute()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": "stock.gl.recon.line",
            "view_mode": "list,form",
            # ไม่เอาแถว "รวม" ขึ้น list เพราะหัวกลุ่ม (group by section) รวมยอดให้อยู่แล้ว
            # ถ้าใส่มาด้วยหัวกลุ่มจะโชว์เบิ้ล 2 เท่า (เจอ 23 ก.ย. 2026) — PDF/Excel ยังใช้แถวรวมตามเดิม
            "domain": [("wizard_id", "=", self.id), ("is_total", "=", False)],
            "context": {"group_by": ["section"], "create": False, "edit": False, "delete": False},
        }

    def action_print_pdf(self):
        self.ensure_one()
        self._ensure_lines()
        return self.env.ref("custom_stock_gl_recon.action_report_stock_gl_recon").report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        lines = self._ensure_lines()
        data = self._build_xlsx(lines)
        attachment = self.env["ir.attachment"].create({
            "name": "StockGLRecon_%s.xlsx" % self.date_to.strftime("%Y%m%d"),
            "type": "binary", "datas": base64.b64encode(data),
            "res_model": self._name, "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {"type": "ir.actions.act_url",
                "url": "/web/content/%d?download=true" % attachment.id, "target": "self"}

    def thai_date(self, d):
        return thai_date(d)

    def valuation_lines(self):
        return self.line_ids.filtered(lambda l: l.section == "valuation")

    def suspense_lines(self):
        return self.line_ids.filtered(lambda l: l.section == "suspense")

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------
    def _build_xlsx(self, lines):
        import xlsxwriter

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        f_title = wb.add_format({"bold": True, "font_size": 14})
        f_head = wb.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1, "align": "center",
                                "valign": "vcenter", "text_wrap": True})
        f_text = wb.add_format({"border": 1})
        f_num = wb.add_format({"border": 1, "num_format": "#,##0.00;[Red]-#,##0.00"})
        f_tot = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA"})
        f_tot_n = wb.add_format({"border": 1, "bold": True, "bg_color": "#E2EFDA",
                                 "num_format": "#,##0.00;[Red]-#,##0.00"})
        sub = "ณ วันที่ %s" % self.date_to.strftime("%d/%m/%Y")

        ws = wb.add_worksheet("A บัญชีสินค้า")
        ws.write(0, 0, "กระทบยอดสต็อกกับบัญชี - ส่วน A บัญชีสินค้าคงเหลือ", f_title)
        ws.write(1, 0, sub)
        heads = [("รหัสบัญชี", 10), ("ชื่อบัญชี", 30), ("ของในคลัง (จำนวน×ต้นทุน)", 16), ("ระบบสต็อก (SVL)", 16),
                 ("ยอดในบัญชี (GL)", 16), ("บัญชี − ระบบสต็อก", 16),
                 ("สาเหตุ: สต็อกไม่ลงบัญชี (SVL ไม่มี JE)", 18), ("ในนั้นเป็นสินค้าไม่เก็บสต็อก", 16),
                 ("สาเหตุ: บัญชีไม่ได้มาจากสต็อก (JE ไม่มี SVL)", 18), ("สาเหตุ: ผูกกันแต่ยอด/วันที่ไม่ตรง", 16),
                 ("ระบบสต็อก − ของในคลัง", 16), ("จำนวนสินค้า", 10)]
        hr = 3
        for c, (h, w) in enumerate(heads):
            ws.write(hr, c, h, f_head)
            ws.set_column(c, c, w)
        ws.set_row(hr, 45)
        r = hr + 1
        for l in self.valuation_lines():
            ft, fn = (f_tot, f_tot_n) if l.is_total else (f_text, f_num)
            ws.write(r, 0, l.account_code or "", ft)
            ws.write(r, 1, l.account_name or "", ft)
            for c, k in enumerate(["physical_value", "svl_value", "gl_value", "diff_gl_svl", "svl_no_je",
                                   "svl_non_storable", "je_no_svl", "linked_diff", "diff_svl_phys"], 2):
                ws.write_number(r, c, l[k], fn)
            ws.write_number(r, 11, l.product_count, ft)
            r += 1
        r += 1
        ws.write(r, 0, "ส่วน B บัญชีพักสินค้าขาเข้า / ขาออก", f_title); r += 1
        bheads = [("รหัสบัญชี", 10), ("ชื่อบัญชี", 30), ("ประเภท", 12), ("ยอดคงค้าง (GL)", 16),
                  ("มาจากใบรับ/ใบส่ง (SVL)", 16), ("ลงมือ / จากบิล-JV", 16), ("ยังไม่จับคู่", 16), ("เปิด Allow Reconciliation", 14)]
        for c, (h, w) in enumerate(bheads):
            ws.write(r, c, h, f_head)
        r += 1
        for l in self.suspense_lines():
            ws.write(r, 0, l.account_code or "", f_text)
            ws.write(r, 1, l.account_name or "", f_text)
            ws.write(r, 2, "ขาเข้า" if l.suspense_kind == "input" else "ขาออก", f_text)
            ws.write_number(r, 3, l.gl_value, f_num)
            ws.write_number(r, 4, l.gl_linked, f_num)
            ws.write_number(r, 5, l.je_no_svl, f_num)
            ws.write_number(r, 6, l.gl_unreconciled, f_num)
            ws.write(r, 7, "ใช่" if l.is_reconcilable else "ไม่", f_text)
            r += 1

        wp = wb.add_worksheet("รายสินค้า")
        wp.write(0, 0, "ระบบสต็อก (SVL) เทียบของในคลัง รายสินค้า", f_title)
        wp.write(1, 0, sub)
        pheads = [("บัญชี", 10), ("รหัสสินค้า", 14), ("ชื่อสินค้า", 38), ("หมวด", 22), ("เก็บสต็อก", 8), ("หมวด Manual", 8),
                  ("คงเหลือ (คลัง)", 11), ("จำนวนใน SVL", 11), ("ต้นทุน/หน่วย", 11), ("ของในคลัง", 14), ("SVL", 14),
                  ("SVL ไม่มี JE", 14), ("SVL − ของในคลัง", 14)]
        for c, (h, w) in enumerate(pheads):
            wp.write(hr, c, h, f_head)
            wp.set_column(c, c, w)
        wp.freeze_panes(hr + 1, 3)
        r = hr + 1
        for l in self.valuation_lines():
            for d in l.detail_ids.filtered(lambda d: d.kind == "product"):
                wp.write(r, 0, l.account_code or "-", f_text)
                wp.write(r, 1, d.product_id.default_code or "", f_text)
                wp.write(r, 2, d.product_id.name or "", f_text)
                wp.write(r, 3, d.categ_id.complete_name or "", f_text)
                wp.write(r, 4, "ใช่" if d.is_storable else "ไม่", f_text)
                wp.write(r, 5, "ใช่" if d.is_manual else "ไม่", f_text)
                for c, k in enumerate(["qty", "svl_qty", "unit_cost", "physical_value", "svl_value", "svl_no_je", "diff_value"], 6):
                    wp.write_number(r, c, d[k], f_num)
                r += 1
        wp.autofilter(hr, 0, max(r - 1, hr), len(pheads) - 1)

        wj = wb.add_worksheet("รายสมุด")
        wj.write(0, 0, "ยอดบัญชีแยกตามสมุดรายวัน และมาจากระบบสต็อกหรือไม่", f_title)
        wj.write(1, 0, sub)
        jheads = [("บัญชี", 10), ("ชื่อบัญชี", 26), ("สมุดรายวัน", 24), ("มาจากระบบสต็อก", 10), ("เดบิต", 14),
                  ("เครดิต", 14), ("คงเหลือ", 14), ("บรรทัด", 8), ("ยังไม่จับคู่", 14)]
        for c, (h, w) in enumerate(jheads):
            wj.write(hr, c, h, f_head)
            wj.set_column(c, c, w)
        r = hr + 1
        for l in lines:
            for d in l.detail_ids.filtered(lambda d: d.kind == "journal"):
                wj.write(r, 0, l.account_code or "", f_text)
                wj.write(r, 1, l.account_name or "", f_text)
                wj.write(r, 2, d.journal_id.display_name or "", f_text)
                wj.write(r, 3, "ใช่" if d.linked else "ไม่", f_text)
                wj.write_number(r, 4, d.debit, f_num)
                wj.write_number(r, 5, d.credit, f_num)
                wj.write_number(r, 6, d.balance, f_num)
                wj.write_number(r, 7, d.line_count, f_text)
                wj.write_number(r, 8, d.unreconciled, f_num)
                r += 1
        wj.autofilter(hr, 0, max(r - 1, hr), len(jheads) - 1)
        wb.close()
        return buf.getvalue()


class StockGlReconLine(models.TransientModel):
    _name = "stock.gl.recon.line"
    _description = "กระทบยอดสต็อกกับบัญชี - ต่อบัญชี"
    _order = "sequence, id"

    wizard_id = fields.Many2one("stock.gl.recon.wizard", required=True, ondelete="cascade")
    sequence = fields.Integer()
    section = fields.Selection([("valuation", "A บัญชีสินค้าคงเหลือ"), ("suspense", "B บัญชีพักขาเข้า/ขาออก")], string="ส่วน")
    is_total = fields.Boolean("แถวรวม")
    account_id = fields.Many2one("account.account", "บัญชี")
    account_code = fields.Char("รหัสบัญชี")
    account_name = fields.Char("ชื่อบัญชี")
    suspense_kind = fields.Selection([("input", "ขาเข้า"), ("output", "ขาออก")], string="ประเภทบัญชีพัก")
    physical_value = fields.Float("ของในคลัง (จำนวน×ต้นทุน)", digits=(16, 2))
    svl_value = fields.Float("ระบบสต็อก (SVL)", digits=(16, 2))
    gl_value = fields.Float("ยอดในบัญชี (GL)", digits=(16, 2))
    diff_gl_svl = fields.Float("บัญชี − ระบบสต็อก", digits=(16, 2))
    svl_no_je = fields.Float("สต็อกไม่ลงบัญชี (SVL ไม่มี JE)", digits=(16, 2))
    svl_non_storable = fields.Float("ในนั้น: สินค้าไม่เก็บสต็อก", digits=(16, 2))
    je_no_svl = fields.Float("บัญชีไม่ได้มาจากสต็อก (JE ไม่มี SVL)", digits=(16, 2))
    linked_diff = fields.Float("ผูกกันแต่ยอด/วันที่ไม่ตรง", digits=(16, 2))
    diff_svl_phys = fields.Float("ระบบสต็อก − ของในคลัง", digits=(16, 2))
    gl_linked = fields.Float("มาจากใบรับ/ใบส่ง (SVL)", digits=(16, 2))
    gl_unreconciled = fields.Float("ยังไม่จับคู่", digits=(16, 2))
    is_reconcilable = fields.Boolean("เปิด Allow Reconciliation")
    product_count = fields.Integer("จำนวนสินค้า")
    detail_ids = fields.One2many("stock.gl.recon.detail", "line_id")
    product_detail_ids = fields.One2many("stock.gl.recon.detail", "line_id", domain=[("kind", "=", "product")])
    journal_detail_ids = fields.One2many("stock.gl.recon.detail", "line_id", domain=[("kind", "=", "journal")])
    name = fields.Char(compute="_compute_name")
    date_to = fields.Date(related="wizard_id.date_to")

    @api.depends("account_code", "account_name")
    def _compute_name(self):
        for l in self:
            l.name = ("%s %s" % (l.account_code or "", l.account_name or "")).strip()


class StockGlReconDetail(models.TransientModel):
    _name = "stock.gl.recon.detail"
    _description = "กระทบยอดสต็อกกับบัญชี - รายละเอียด"
    _order = "sequence, id"

    line_id = fields.Many2one("stock.gl.recon.line", required=True, ondelete="cascade")
    sequence = fields.Integer()
    kind = fields.Selection([("product", "รายสินค้า"), ("journal", "รายสมุดรายวัน")], string="ชนิด")
    # product
    product_id = fields.Many2one("product.product", "สินค้า")
    default_code = fields.Char(related="product_id.default_code", string="รหัสสินค้า")
    categ_id = fields.Many2one("product.category", "หมวด")
    is_storable = fields.Boolean("เก็บสต็อก")
    is_manual = fields.Boolean("หมวด Manual")
    qty = fields.Float("คงเหลือ (คลัง)", digits=(16, 2))
    svl_qty = fields.Float("จำนวนใน SVL", digits=(16, 2))
    unit_cost = fields.Float("ต้นทุน/หน่วย", digits=(16, 2))
    physical_value = fields.Float("ของในคลัง", digits=(16, 2))
    svl_value = fields.Float("SVL", digits=(16, 2))
    svl_no_je = fields.Float("SVL ไม่มี JE", digits=(16, 2))
    diff_value = fields.Float("SVL − ของในคลัง", digits=(16, 2))
    # journal
    journal_id = fields.Many2one("account.journal", "สมุดรายวัน")
    linked = fields.Boolean("มาจากระบบสต็อก (SVL)")
    debit = fields.Float("เดบิต", digits=(16, 2))
    credit = fields.Float("เครดิต", digits=(16, 2))
    balance = fields.Float("คงเหลือ", digits=(16, 2))
    line_count = fields.Integer("บรรทัด")
    unreconciled = fields.Float("ยังไม่จับคู่", digits=(16, 2))

    def action_open_aml(self):
        """เปิดบรรทัดบัญชีของสมุดนี้บนบัญชีนี้ (ณ วันที่)"""
        self.ensure_one()
        line = self.line_id
        domain = [("account_id", "=", line.account_id.id), ("journal_id", "=", self.journal_id.id),
                  ("parent_state", "=", "posted"), ("date", "<=", line.date_to)]
        return {"type": "ir.actions.act_window", "name": "%s / %s" % (line.name, self.journal_id.display_name),
                "res_model": "account.move.line", "view_mode": "list,form", "domain": domain,
                "context": {"create": False}}

    def action_open_svl(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": self.product_id.display_name,
                "res_model": "stock.valuation.layer", "view_mode": "list,form",
                "domain": [("product_id", "=", self.product_id.id)], "context": {"create": False}}
