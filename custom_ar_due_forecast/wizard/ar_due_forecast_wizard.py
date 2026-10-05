# -*- coding: utf-8 -*-
"""คาดรับเงินลูกหนี้รายวัน (AR Due Forecast)

หลักการ
-------
* แหล่งข้อมูล = account.move ประเภท out_invoice / out_refund ที่ state = posted
  (ใบลดหนี้ติดลบ หักออกจากยอดของวันนั้น)
* ช่องวัน = amount_total_signed ของใบที่ invoice_date_due อยู่ในวันนั้น (รวมใบที่รับเงินแล้ว
  เพื่อให้เดือนที่ผ่านไปแล้วยังดูได้ว่า คาดไว้เท่าไร รับจริงเท่าไร)
* ค้างยกมา = amount_residual_signed ของใบที่ครบกำหนดก่อนวันแรกของเดือน และยังไม่จ่ายครบ
* จำนวนเงิน (รับแล้ว) = amount_total_signed - amount_residual_signed ของใบในเดือน
  วันที่รับเงิน = วันที่ล่าสุดของรายการที่มาจับคู่ (account.partial.reconcile)
* Due (วันเครดิต) = เงื่อนไขชำระเงินของลูกค้า ถ้าไม่ได้ตั้ง → ค่าที่พบบ่อยสุดของ
  (วันครบกำหนด - วันที่ใบ) ใน 12 เดือนล่าสุด; 0 = ไม่แสดง
* แถวลูกค้า = ลูกค้าที่มีใบครบกำหนดในเดือน ∪ มีใบค้างยกมา ∪ มีใบเปิดอยู่ (ครบกำหนดเดือนหน้า)
  ∪ ออกใบใน recent_months เดือนล่าสุด (แถวว่าง)
"""
import base64
import io
import logging
from collections import Counter, defaultdict
from datetime import date, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

THAI_MONTHS = [
    "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]
THAI_MONTHS_SHORT = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

def _be(d):
    """วันที่ → dd/mm/yy พ.ศ. (18/09/69)"""
    return "%02d/%02d/%02d" % (d.day, d.month, (d.year + 543) % 100)


class ArDueForecastWizard(models.TransientModel):
    _name = "ar.due.forecast.wizard"
    _description = "คาดรับเงินลูกหนี้รายวัน"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    month_date = fields.Date(
        string="เดือนที่ต้องการ", required=True,
        default=lambda self: (fields.Date.context_today(self).replace(day=1)
                              + timedelta(days=32)).replace(day=1),
        help="เลือกวันใดก็ได้ในเดือนนั้น (ค่าเริ่มต้น = เดือนหน้า)",
    )
    as_of_date = fields.Date(
        string="ณ วันที่", required=True,
        default=fields.Date.context_today,
        help="พิมพ์ลงหัวรายงานเท่านั้น ตัวเลขใช้ข้อมูลปัจจุบันในระบบ",
    )
    recent_months = fields.Integer(
        string="แสดงลูกค้าที่ออกใบใน (เดือนล่าสุด)", default=3,
        help="ลูกค้าที่ออกใบแจ้งหนี้ในช่วงนี้จะมีแถวในรายงานแม้ยังไม่มียอดครบกำหนดในเดือนที่เลือก "
             "(ศูนย์ที่เครดิตยาว ยังไม่ออกใบ → แถวว่าง) ใส่ 0 = ไม่แสดง",
    )
    partner_ids = fields.Many2many(
        "res.partner", string="เฉพาะลูกค้า",
        help="เว้นว่าง = ทุกลูกค้า",
    )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _month_range(self):
        start = self.month_date.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        return start, end

    def _partner_due_days(self, partner, sample):
        """วันเครดิตของลูกค้า: จากเงื่อนไขชำระเงิน ถ้าไม่มีดูจากใบที่ผ่านมา"""
        term = partner.with_company(self.company_id).property_payment_term_id
        if term:
            lines = term.line_ids
            if len(lines) == 1 and lines.delay_type == "days_after":
                return str(int(lines.nb_days))
            return term.name
        if sample:
            days, cnt = Counter(sample).most_common(1)[0]
            return str(days) if days > 0 else ""
        return ""

    def _billing_map(self):
        """move_id → ใบวางบิลล่าสุดที่ไม่ถูกยกเลิก {name, date, promise}"""
        # อ่านด้วย SQL → เขียนค่าที่ค้างใน cache ลงฐานก่อน (เช่น เพิ่งแก้วันนัด)
        self.env["customer.billing.note"].flush_model()
        self.env.cr.execute(
            """
            SELECT DISTINCT ON (r.move_id) r.move_id, b.name, b.date, b.promise_date
              FROM billing_note_move_rel r
              JOIN customer_billing_note b ON b.id = r.billing_id
             WHERE b.state != 'cancel'
             ORDER BY r.move_id, b.date DESC, b.id DESC
            """
        )
        return {
            mid: {"name": name, "date": bdate, "promise": promise}
            for mid, name, bdate, promise in self.env.cr.fetchall()
        }

    @staticmethod
    def _expected_date(move, bn):
        """วันที่คาดว่าจะได้รับเงิน = วันนัดรับชำระในใบวางบิล ถ้ามี ไม่งั้นวันครบกำหนดของใบแจ้งหนี้"""
        return (bn and bn["promise"]) or move.invoice_date_due

    def _base_domain(self):
        domain = [
            ("company_id", "=", self.company_id.id),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
        ]
        if self.partner_ids:
            domain.append(("partner_id", "in", self.partner_ids.ids))
        return domain

    def _collect_moves(self):
        """คืน (month_list, open_list, bn_map)
        month_list = [(move, วันคาดรับ)] ที่วันคาดรับอยู่ในเดือน (ทุก payment_state)
        open_list  = [(move, วันคาดรับ)] ใบที่ยังค้างรับทั้งหมด (ใช้หาค้างยกมา / เดือนถัดไป)"""
        self.ensure_one()
        start, end = self._month_range()
        Move = self.env["account.move"]
        base_domain = self._base_domain()
        bn_map = self._billing_map()
        # ใบที่วันนัดในใบวางบิลตกในเดือนนี้ (อาจครบกำหนดเดิมคนละเดือน)
        promised_in_month = [mid for mid, bn in bn_map.items()
                             if bn["promise"] and start <= bn["promise"] <= end]
        # ใบ 0 บาท (ขายราคา 0 ใช้เบิกของ) ไม่ใช่รายได้ → ตัดออก
        candidates = Move.search(
            base_domain + [("amount_total", "!=", 0), "|",
                           "&", ("invoice_date_due", ">=", start), ("invoice_date_due", "<=", end),
                           ("id", "in", promised_in_month)]
        )
        month_list = []
        for m in candidates:
            eff = self._expected_date(m, bn_map.get(m.id))
            if eff and start <= eff <= end:
                month_list.append((m, eff))
        open_moves = Move.search(
            base_domain + [("payment_state", "in", ("not_paid", "partial"))]
        )
        open_list = []
        for m in open_moves:
            eff = self._expected_date(m, bn_map.get(m.id))
            if eff:
                open_list.append((m, eff))
        return month_list, open_list, bn_map

    def _fetch_data(self):
        """คืน dict partner_id → ข้อมูลแถว + list ใบรายละเอียด"""
        self.ensure_one()
        start, end = self._month_range()
        Move = self.env["account.move"]
        base_domain = self._base_domain()

        # 1) ใบที่คาดรับในเดือน  2) ใบเปิดอยู่ทั้งหมด (ค้างยกมา + เดือนถัดไป)
        month_list, open_list, bn_map = self._collect_moves()
        month_moves = Move.browse([m.id for m, _e in month_list])
        # 3) ลูกค้าที่ออกใบใน N เดือนล่าสุด (แถวว่าง)
        recent_partner_ids = set()
        if self.recent_months > 0:
            since = (self.as_of_date.replace(day=1) - timedelta(days=1)).replace(day=1)
            for _i in range(self.recent_months - 1):
                since = (since - timedelta(days=1)).replace(day=1)
            groups = Move._read_group(
                base_domain + [("invoice_date", ">=", since), ("amount_total", "!=", 0)],
                ["partner_id"], []
            )
            recent_partner_ids = {g[0].id for g in groups if g[0]}

        # วันที่รับเงินล่าสุดต่อใบ (จาก partial reconcile ทั้งสองฝั่ง)
        pay_date = {}
        month_ids = tuple(month_moves.ids)
        if month_ids:
            self.env.cr.execute(
                """
                SELECT l.move_id, MAX(cm.date)
                  FROM account_partial_reconcile pr
                  JOIN account_move_line l  ON l.id IN (pr.debit_move_id, pr.credit_move_id)
                  JOIN account_move_line cl ON cl.id IN (pr.debit_move_id, pr.credit_move_id)
                                           AND cl.id <> l.id
                  JOIN account_move cm ON cm.id = cl.move_id
                 WHERE l.move_id IN %s
                 GROUP BY l.move_id
                """,
                (month_ids,),
            )
            pay_date = dict(self.env.cr.fetchall())

        # ตัวอย่างวันเครดิตจากใบ 12 เดือนล่าสุด
        sample_days = defaultdict(list)
        since12 = self.as_of_date - timedelta(days=365)
        self.env.cr.execute(
            """
            SELECT partner_id, (invoice_date_due - invoice_date)
              FROM account_move
             WHERE company_id = %s AND move_type = 'out_invoice' AND state = 'posted'
               AND invoice_date >= %s AND invoice_date_due IS NOT NULL AND invoice_date IS NOT NULL
               AND amount_total <> 0
            """,
            (self.company_id.id, since12),
        )
        for pid, days in self.env.cr.fetchall():
            sample_days[pid].append(days)

        rows = {}

        def row(partner):
            if partner.id not in rows:
                rows[partner.id] = {
                    "partner": partner,
                    "days": defaultdict(float),   # day → amount
                    "days_unbilled": set(),       # วันที่มียอดที่ยังไม่วางบิล
                    "carry_unbilled": False,
                    "carry": 0.0,
                    "carry_count": 0,
                    "carry_oldest": None,
                    "future": 0.0,
                    "future_count": 0,
                    "received": 0.0,
                    "pay_date": None,
                    "count": 0,
                    "invoices": [],
                }
            return rows[partner.id]

        for m, eff in month_list:
            r = row(m.partner_id)
            bn = bn_map.get(m.id)
            r["days"][eff.day] += m.amount_total_signed
            if not bn:
                r["days_unbilled"].add(eff.day)
            r["received"] += m.amount_total_signed - m.amount_residual_signed
            r["count"] += 1
            pd = pay_date.get(m.id)
            if pd and (not r["pay_date"] or pd > r["pay_date"]):
                r["pay_date"] = pd
            r["invoices"].append(("เดือนนี้", m, pd, eff, bn))
        for m, eff in open_list:
            r = row(m.partner_id)
            bn = bn_map.get(m.id)
            if eff < start:
                r["carry"] += m.amount_residual_signed
                r["carry_count"] += 1
                if not bn:
                    r["carry_unbilled"] = True
                if not r["carry_oldest"] or eff < r["carry_oldest"]:
                    r["carry_oldest"] = eff
                r["invoices"].append(("ค้างยกมา", m, None, eff, bn))
            elif eff > end:
                r["future"] += m.amount_residual_signed
                r["future_count"] += 1
                r["invoices"].append(("คาดรับหลังเดือนนี้", m, None, eff, bn))
        if recent_partner_ids:
            for p in self.env["res.partner"].browse(list(recent_partner_ids - set(rows))):
                row(p)

        for r in rows.values():
            p = r["partner"]
            r["due"] = self._partner_due_days(p, sample_days.get(p.id))
            r["days"] = {d: round(v, 2) for d, v in r["days"].items() if round(v, 2)}
            r["days_unbilled"] = {d for d in r["days_unbilled"] if d in r["days"]}
            r["carry"] = round(r["carry"], 2)
            r["future"] = round(r["future"], 2)
            r["received"] = round(r["received"], 2)
            r["month_total"] = round(sum(r["days"].values()), 2)
            note = []
            if r["count"]:
                note.append("%d ใบ" % r["count"])
            if r["carry_count"]:
                note.append(
                    "ค้างยกมา %d ใบ (เก่าสุดคาดรับ %s)" % (r["carry_count"], _be(r["carry_oldest"]))
                )
            if r["future_count"]:
                note.append("คาดรับเดือนถัดไป %s บาท (%d ใบ)"
                            % ("{:,.2f}".format(r["future"]), r["future_count"]))
            r["note"] = ", ".join(note)

        ordered = sorted(rows.values(), key=lambda r: (r["partner"].name or "", r["partner"].id))
        return ordered

    def _partner_label(self, partner):
        name = partner.name or ""
        branch = (getattr(partner, "branch", "") or "").strip()
        if branch.isdigit() and int(branch) > 0 and "สาขา" not in name:
            name += " (สาขาที่ %s)" % branch
        return name

    def _fetch_cash(self):
        """เงินสดรับจริงในเดือน = ใบเสร็จ (out_receipt เช่น CT จากสมุด Cash Receipt VAT/Non-VAT)
        ลงช่องตามวันที่ใบเสร็จ (= วันรับเงิน) — เดือนอนาคตจะว่าง"""
        self.ensure_one()
        start, end = self._month_range()
        moves = self.env["account.move"].search([
            ("company_id", "=", self.company_id.id),
            ("move_type", "=", "out_receipt"),
            ("state", "=", "posted"),
            ("invoice_date", ">=", start),
            ("invoice_date", "<=", end),
            ("amount_total", "!=", 0),
        ], order="invoice_date, name")
        days = defaultdict(float)
        for m in moves:
            days[m.invoice_date.day] += m.amount_total_signed
        days = {d: round(v, 2) for d, v in days.items() if round(v, 2)}
        return {
            "moves": moves,
            "days": days,
            "total": round(sum(days.values()), 2),
            "last_date": max(moves.mapped("invoice_date")) if moves else None,
        }

    # ------------------------------------------------------------------
    # หน้ารายงานบนจอ (client action แบบ P&L)
    # ------------------------------------------------------------------
    # หน้ารายงานบนจอ (client action แบบ P&L)
    # ------------------------------------------------------------------
    @api.model
    def get_screen_data(self, month=None):
        """month = 'YYYY-MM' (ว่าง = เดือนหน้า) → ข้อมูลตารางเดียวกับ PDF"""
        vals = {"as_of_date": fields.Date.context_today(self)}
        if month:
            y, m = month.split("-")[:2]
            vals["month_date"] = date(int(y), int(m), 1)
        wiz = self.create(vals)
        start, _end = wiz._month_range()
        data = wiz._report_data()
        data.update({
            "wizard_id": wiz.id,
            "month": "%04d-%02d" % (start.year, start.month),
            "company": wiz.company_id.name,
        })
        return data

    @api.model
    def action_open_moves(self, month, kind, partner_id=False, day=False):
        """คลิกตัวเลขบนจอ → รายการใบแจ้งหนี้ที่อยู่เบื้องหลัง
        kind: carry (ค้างยกมา) / day (คาดรับวันนั้น) / month (คาดรับทั้งเดือน) / cash (ใบเสร็จเงินสด)"""
        y, m = month.split("-")[:2]
        start = date(int(y), int(m), 1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        if kind == "cash":
            # ใบเสร็จเงินสด (CT) ของวันนั้น / ทั้งเดือน
            domain = [
                ("company_id", "=", self.env.company.id),
                ("move_type", "=", "out_receipt"),
                ("state", "=", "posted"),
                ("amount_total", "!=", 0),
            ]
            if day:
                d = date(start.year, start.month, int(day))
                domain.append(("invoice_date", "=", d))
                title = "ลูกค้าเงินสด: ใบเสร็จวันที่ %s" % _be(d)
            else:
                domain += [("invoice_date", ">=", start), ("invoice_date", "<=", end)]
                title = "ลูกค้าเงินสด: ใบเสร็จเดือน %s %d" % (
                    THAI_MONTHS[start.month], start.year + 543)
            return {
                "type": "ir.actions.act_window",
                "name": title,
                "res_model": "account.move",
                "views": [(self.env.ref("account.view_out_invoice_tree").id, "list"),
                          (False, "form")],
                "domain": domain,
                "context": {"create": False, "default_move_type": "out_receipt"},
            }
        # ใช้ชุดใบเดียวกับตาราง (วันคาดรับ = วันนัดในใบวางบิล หรือวันครบกำหนด)
        vals = {"month_date": start}
        if partner_id:
            vals["partner_ids"] = [(6, 0, [partner_id])]
        wiz = self.create(vals)
        month_list, open_list, _bn = wiz._collect_moves()
        if kind == "carry":
            ids = [mv.id for mv, eff in open_list if eff < start]
            title = "ค้างยกมา (เลยวันคาดรับก่อน %s)" % _be(start)
        elif kind == "day" and day:
            d = date(start.year, start.month, int(day))
            ids = [mv.id for mv, eff in month_list if eff == d]
            title = "คาดรับ %s" % _be(d)
        else:
            ids = [mv.id for mv, _eff in month_list]
            title = "คาดรับเดือน %s %d" % (THAI_MONTHS[start.month], start.year + 543)
        if partner_id:
            title = "%s: %s" % (self.env["res.partner"].browse(partner_id).name, title)
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "account.move",
            "views": [(self.env.ref("custom_ar_due_forecast.view_ar_forecast_move_list").id, "list"),
                      (False, "form")],
            "domain": [("id", "in", ids)],
            "context": {"create": False, "default_move_type": "out_invoice"},
        }

    def action_export_xlsx(self):
        self.ensure_one()
        data = self._build_xlsx(self._fetch_data())
        start, _end = self._month_range()
        fname = "AR_Forecast_%04d-%02d.xlsx" % (start.year, start.month)
        attachment = self.env["ir.attachment"].create({
            "name": fname,
            "type": "binary",
            "datas": base64.b64encode(data),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%d?download=true" % attachment.id,
            "target": "self",
        }

    # ------------------------------------------------------------------
    # PDF - แสดงเฉพาะข้อมูลที่มี
    # ------------------------------------------------------------------
    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(
            "custom_ar_due_forecast.action_report_ar_due_forecast"
        ).report_action(self)

    def _report_data(self):
        """ข้อมูลสำหรับ PDF: ตัดลูกค้า / วัน / คอลัมน์ที่ไม่มียอดออก"""
        self.ensure_one()
        start, _end = self._month_range()

        def fmt(v):
            return "{:,.2f}".format(v) if v else ""

        rows = [
            r for r in self._fetch_data()
            if r["carry"] or r["month_total"] or r["received"]
        ]
        cash = self._fetch_cash()
        has_cash = bool(cash["total"])
        days = sorted({d for r in rows for d in r["days"]} | set(cash["days"]))
        show_carry = any(r["carry"] for r in rows)
        show_recv = has_cash or any(r["received"] for r in rows)
        show_paydate = has_cash or any(r["pay_date"] for r in rows)
        show_due = any(r["due"] for r in rows)

        out_rows = []
        tot_days = defaultdict(float)
        tot = {"carry": 0.0, "month": 0.0, "recv": 0.0, "out": 0.0}
        for i, r in enumerate(rows, start=1):
            outstanding = round(r["month_total"] - r["received"], 2)
            for d, v in r["days"].items():
                tot_days[d] += v
            tot["carry"] += r["carry"]
            tot["month"] += r["month_total"]
            tot["recv"] += r["received"]
            tot["out"] += outstanding
            out_rows.append({
                "seq": i,
                "partner_id": r["partner"].id,
                "full_name": self._partner_label(r["partner"]),
                "name": self._short_name(self._partner_label(r["partner"])),
                "due": r["due"],
                "carry": fmt(r["carry"]),
                "days": [fmt(r["days"].get(d)) for d in days],
                # True = ช่องนี้มียอดที่ยังไม่อยู่ในใบวางบิล (แสดงสีส้ม)
                "days_unbilled": [d in r["days_unbilled"] for d in days],
                "carry_unbilled": r["carry_unbilled"],
                "month": fmt(r["month_total"]),
                "pay_date": _be(r["pay_date"]) if r["pay_date"] else "",
                "recv": fmt(r["received"]),
                "out": fmt(outstanding),
                "carry_neg": r["carry"] < 0,
                "out_neg": outstanding < 0,
            })
        # หมวด 1 ลูกค้าเงินสด (เฉพาะเมื่อมียอด) + รวมทั้งสิ้น (1-2)
        cash_row = False
        grand = False
        if has_cash:
            cash_row = {
                "days": [fmt(cash["days"].get(d)) for d in days],
                "month": fmt(cash["total"]),
                "recv": fmt(cash["total"]),
                "pay_date": _be(cash["last_date"]) if cash["last_date"] else "",
                "count": len(cash["moves"]),
            }
            grand = {
                "carry": fmt(round(tot["carry"], 2)),
                "days": [fmt(round(tot_days[d] + cash["days"].get(d, 0.0), 2)) for d in days],
                "month": fmt(round(tot["month"] + cash["total"], 2)),
                "recv": fmt(round(tot["recv"] + cash["total"], 2)),
                "out": fmt(round(tot["out"], 2)),
            }
        ncols = (2 + int(show_due) + int(show_carry) + len(days) + 1
                 + int(show_paydate) + 2 * int(show_recv))
        return {
            "ncols": ncols,
            "cash": cash_row,
            "grand": grand,
            "has_ar": bool(out_rows),
            "title": "สรุปยอดรายได้ที่คาดว่าจะได้รับ ตาม DEL กำหนดรับชำระเงิน",
            "period": "เดือน %s %d  ณ วันที่ %s" % (
                THAI_MONTHS[start.month], start.year + 543, _be(self.as_of_date)),
            "days": ["%d %s" % (d, THAI_MONTHS_SHORT[start.month]) for d in days],
            "rows": out_rows,
            "show_carry": show_carry,
            "show_recv": show_recv,
            "show_paydate": show_paydate,
            "show_due": show_due,
            "tot_days": [fmt(round(tot_days[d], 2)) for d in days],
            "tot": {k: fmt(round(v, 2)) for k, v in tot.items()},
            "tot_all": fmt(round(tot["carry"] + tot["month"] + cash["total"], 2)),
            "printed": _be(fields.Date.context_today(self)),
            "dense": len(days) > 12,
            "day_nums": days,
        }

    @staticmethod
    def _short_name(name):
        """ย่อชื่อสำหรับ PDF: ตัดคำนำหน้า/ท้ายนิติบุคคล + เลขสาขา 00002 -> สาขา 2"""
        import re
        n = name
        n = re.sub(r"^(บริษัท|บจก\.|บมจ\.|ห้างหุ้นส่วนจำกัด|หจก\.)\s*", "", n)
        n = re.sub(r"\s*จำกัด\s*\(มหาชน\)", "", n)
        n = re.sub(r"\s*จำกัด", "", n)
        n = re.sub(r"สาขาที่\s*0*(\d+)", r"สาขา \1", n)
        return re.sub(r"\s+", " ", n).strip() or name

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------
    def _build_xlsx(self, rows):
        import xlsxwriter
        from xlsxwriter.utility import xl_col_to_name, xl_rowcol_to_cell

        start, end = self._month_range()
        ndays = end.day
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        sheet_name = "%s%02d" % (THAI_MONTHS_SHORT[start.month], (start.year + 543) % 100)
        ws = wb.add_worksheet(sheet_name)

        base = {"font_name": "Tahoma", "font_size": 9}
        f_title = wb.add_format(dict(base, bold=True, font_size=11, align="center"))
        f_sub = wb.add_format(dict(base, bold=True, align="center"))
        f_head = wb.add_format(dict(base, bold=True, bg_color="#D9E1F2", border=1,
                                    align="center", valign="vcenter", text_wrap=True))
        f_head_day = wb.add_format(dict(base, bold=True, bg_color="#D9E1F2", border=1,
                                        align="center", num_format="d"))
        f_sec = wb.add_format(dict(base, bold=True, bg_color="#FFF2CC", border=1))
        f_txt = wb.add_format(dict(base, border=1))
        f_ctr = wb.add_format(dict(base, border=1, align="center"))
        f_num = wb.add_format(dict(base, border=1, num_format="#,##0.00;[Red]-#,##0.00;"))
        f_date = wb.add_format(dict(base, border=1, num_format="dd/mm/yyyy", align="center"))
        f_tot = wb.add_format(dict(base, border=1, bold=True, bg_color="#E2EFDA"))
        f_tot_num = wb.add_format(dict(base, border=1, bold=True, bg_color="#E2EFDA",
                                       num_format="#,##0.00;[Red]-#,##0.00;"))
        f_grand = wb.add_format(dict(base, border=1, bold=True, bg_color="#BDD7EE"))
        f_grand_num = wb.add_format(dict(base, border=1, bold=True, bg_color="#BDD7EE",
                                         num_format="#,##0.00;[Red]-#,##0.00;"))
        f_note = wb.add_format(dict(base, border=1, text_wrap=False))
        # ยอดที่ยังไม่อยู่ในใบวางบิล = พื้นส้ม
        f_num_unb = wb.add_format(dict(base, border=1, bg_color="#FCE4D6", font_color="#C65911",
                                       num_format="#,##0.00;[Red]-#,##0.00;"))
        f_legend = wb.add_format(dict(base, italic=True, font_color="#595959"))
        f_legend_unb = wb.add_format(dict(base, border=1, bg_color="#FCE4D6", font_color="#C65911"))

        # คอลัมน์
        C_SEQ, C_NAME, C_DUE, C_CARRY = 0, 1, 2, 3
        C_DAY0 = 4                       # วันที่ 1
        C_SUM = C_DAY0 + ndays           # รวม
        C_GAP = C_SUM + 1
        C_PAYDATE = C_GAP + 1
        C_RECV = C_PAYDATE + 1
        C_OUT = C_RECV + 1
        C_NOTE = C_OUT + 1
        last_col = C_NOTE

        ws.set_column(C_SEQ, C_SEQ, 6)
        ws.set_column(C_NAME, C_NAME, 38)
        ws.set_column(C_DUE, C_DUE, 6)
        ws.set_column(C_CARRY, C_CARRY, 13)
        ws.set_column(C_DAY0, C_SUM - 1, 11)
        ws.set_column(C_SUM, C_SUM, 14)
        ws.set_column(C_GAP, C_GAP, 2)
        ws.set_column(C_PAYDATE, C_PAYDATE, 11)
        ws.set_column(C_RECV, C_OUT, 13)
        ws.set_column(C_NOTE, C_NOTE, 45)

        # หัวรายงาน
        ws.merge_range(0, 0, 0, C_SUM, self.company_id.name, f_title)
        ws.merge_range(1, 0, 1, C_SUM,
                       "สรุปยอดรายได้ที่คาดว่าจะได้รับ ตาม DEL กำหนดรับชำระเงิน", f_sub)
        ws.merge_range(2, 0, 2, C_SUM,
                       "เดือน  %s %d  ณ.วันที่  %s"
                       % (THAI_MONTHS[start.month], start.year + 543, _be(self.as_of_date)),
                       f_sub)
        HR = 3
        ws.set_row(HR, 28)
        ws.write(HR, C_SEQ, "ลำดับที่", f_head)
        ws.write(HR, C_NAME, "รายการ", f_head)
        ws.write(HR, C_DUE, "Due", f_head)
        ws.write(HR, C_CARRY, "ค้างยกมา\n(เลยกำหนด)", f_head)
        for d in range(1, ndays + 1):
            ws.write_datetime(HR, C_DAY0 + d - 1, date(start.year, start.month, d), f_head_day)
        ws.write(HR, C_SUM, "รวม", f_head)
        ws.write(HR, C_PAYDATE, "วันที่รับเงิน", f_head)
        ws.write(HR, C_RECV, "จำนวนเงิน", f_head)
        ws.write(HR, C_OUT, "จำนวนเงินคงค้าง", f_head)
        ws.write(HR, C_NOTE, "หมายเหตุ", f_head)
        ws.freeze_panes(HR + 1, C_DAY0)

        num_cols = list(range(C_CARRY, C_SUM + 1)) + [C_RECV, C_OUT]

        def cell(r, c):
            return xl_rowcol_to_cell(r, c)

        def write_data_row(r, seq, name, due="", days=None, carry=None, received=None,
                           pay_date=None, note="", fmt_txt=f_txt, fmt_num=f_num,
                           unbilled_days=(), carry_unbilled=False):
            ws.write(r, C_SEQ, seq if seq else "", f_ctr)
            ws.write(r, C_NAME, name, fmt_txt)
            ws.write(r, C_DUE, due, f_ctr)
            if carry:
                ws.write_number(r, C_CARRY, carry, f_num_unb if carry_unbilled else fmt_num)
            else:
                ws.write_blank(r, C_CARRY, None, fmt_num)
            total = 0.0
            for d in range(1, ndays + 1):
                v = (days or {}).get(d)
                if v:
                    ws.write_number(r, C_DAY0 + d - 1, v,
                                    f_num_unb if d in unbilled_days else fmt_num)
                    total += v
                else:
                    ws.write_blank(r, C_DAY0 + d - 1, None, fmt_num)
            ws.write_formula(r, C_SUM, "=SUM(%s:%s)" % (cell(r, C_DAY0), cell(r, C_SUM - 1)),
                             fmt_num, total)
            if pay_date:
                ws.write_datetime(r, C_PAYDATE, pay_date, f_date)
            else:
                ws.write_blank(r, C_PAYDATE, None, f_date)
            if received:
                ws.write_number(r, C_RECV, received, fmt_num)
            else:
                ws.write_blank(r, C_RECV, None, fmt_num)
            ws.write_formula(r, C_OUT, "=%s-%s" % (cell(r, C_SUM), cell(r, C_RECV)),
                             fmt_num, total - (received or 0.0))
            ws.write(r, C_NOTE, note or "", f_note)

        def write_sum_row(r, label, r0, r1, fmt=f_tot, fmt_num=f_tot_num):
            ws.write(r, C_SEQ, "", fmt)
            ws.write(r, C_NAME, label, fmt)
            ws.write(r, C_DUE, "", fmt)
            for c in range(C_CARRY, last_col + 1):
                if c in num_cols:
                    ws.write_formula(r, c, "=SUM(%s:%s)" % (cell(r0, c), cell(r1, c)), fmt_num)
                else:
                    ws.write(r, c, "", fmt)

        def write_add_row(r, label, rows_to_add, fmt=f_grand, fmt_num=f_grand_num):
            ws.write(r, C_SEQ, "", fmt)
            ws.write(r, C_NAME, label, fmt)
            ws.write(r, C_DUE, "", fmt)
            for c in range(C_CARRY, last_col + 1):
                if c in num_cols:
                    ws.write_formula(r, c, "=" + "+".join(cell(x, c) for x in rows_to_add), fmt_num)
                else:
                    ws.write(r, c, "", fmt)

        def write_section_header(r, label):
            ws.write(r, C_SEQ, label, f_sec)
            for c in range(C_NAME, last_col + 1):
                ws.write(r, c, "", f_sec)

        r = HR + 1
        # ---------- หมวด 1 เงินสด: ยอดรับจริงจากใบเสร็จ (CT) ถ้าไม่มี = แถวว่างไว้กรอกเอง ----------
        cash = self._fetch_cash()
        write_section_header(r, "1. รายได้ - เงินสด")
        r += 1
        cash_row = r
        if cash["total"]:
            write_data_row(
                r, 1, "ลูกค้าเงินสด", days=cash["days"], received=cash["total"],
                pay_date=cash["last_date"],
                note="ใบเสร็จเงินสด %d ใบ (ยอดรับจริง)" % len(cash["moves"]),
            )
        else:
            write_data_row(r, 1, "ลูกค้าเงินสด")
        r += 1
        # ---------- หมวด 2 ลูกหนี้การค้า (จาก Odoo) ----------
        write_section_header(r, "2. รายได้ - ลูกหนี้การค้า(เงินโอน)")
        r += 1
        ar_first = r
        for i, row in enumerate(rows, start=1):
            write_data_row(
                r, i, self._partner_label(row["partner"]), row["due"], row["days"],
                row["carry"], row["received"], row["pay_date"], row["note"],
                unbilled_days=row["days_unbilled"], carry_unbilled=row["carry_unbilled"],
            )
            r += 1
        if not rows:
            write_data_row(r, "", "")
            r += 1
        ar_total = r
        write_sum_row(r, "รวมรายได้ - ลูกหนี้การค้า (2)", ar_first, r - 1)
        r += 1
        write_add_row(r, "รวมรายได้ทั้งสิ้น (1-2)", [cash_row, ar_total])
        r += 2
        # คำอธิบาย
        ws.write(r, C_NAME, "ยังไม่วางบิล", f_legend_unb)
        ws.write(r, C_DUE, "", f_legend)
        ws.write(r, C_CARRY, "= ช่องนี้มียอดของใบแจ้งหนี้ที่ยังไม่อยู่ในใบวางบิล", f_legend)
        r += 1
        ws.write(r, C_CARRY, "ลูกหนี้ลงช่องตาม \"วันนัดรับชำระ\" ในใบวางบิล ถ้าไม่ได้ใส่ ใช้วันครบกำหนดของใบแจ้งหนี้"
                 " · ลูกค้าเงินสด = ยอดรับจริงจากใบเสร็จ", f_legend)

        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.repeat_rows(HR)

        # ---------- ชีทรายละเอียด ----------
        ws2 = wb.add_worksheet("รายละเอียดใบแจ้งหนี้")
        heads = ["ลูกค้า", "กลุ่ม", "เลขที่", "วันที่ใบ", "วันครบกำหนด", "ยอดใบ",
                 "รับแล้ว", "คงค้าง", "วันที่รับเงินล่าสุด", "สถานะจ่าย", "อ้างอิง",
                 "เลขใบวางบิล", "วันที่วางบิล", "วันนัดรับชำระ", "วันคาดรับ (ใช้ในรายงาน)"]
        widths = [38, 18, 14, 11, 11, 13, 13, 13, 13, 10, 20, 13, 11, 12, 13]

        def write_bn_cols(rr, bn, eff):
            if bn:
                ws2.write(rr, 11, bn["name"] or "", f_txt)
                ws2.write_datetime(rr, 12, bn["date"], f_date)
                if bn["promise"]:
                    ws2.write_datetime(rr, 13, bn["promise"], f_date)
                else:
                    ws2.write_blank(rr, 13, None, f_date)
            else:
                ws2.write(rr, 11, "ยังไม่วางบิล", f_legend_unb)
                ws2.write_blank(rr, 12, None, f_date)
                ws2.write_blank(rr, 13, None, f_date)
            if eff:
                ws2.write_datetime(rr, 14, eff, f_date)
            else:
                ws2.write_blank(rr, 14, None, f_date)
        for c, (h, w) in enumerate(zip(heads, widths)):
            ws2.write(0, c, h, f_head)
            ws2.set_column(c, c, w)
        ws2.freeze_panes(1, 0)
        rr = 1
        state_lbl = {"not_paid": "ยังไม่จ่าย", "partial": "จ่ายบางส่วน", "paid": "จ่ายแล้ว",
                     "in_payment": "กำลังจ่าย", "reversed": "กลับรายการ", "invoicing_legacy": "-"}
        for m in cash["moves"]:
            ws2.write(rr, 0, m.partner_id.name or "ลูกค้าเงินสด", f_txt)
            ws2.write(rr, 1, "เงินสด (ใบเสร็จ)", f_txt)
            ws2.write(rr, 2, m.name, f_txt)
            ws2.write_datetime(rr, 3, m.invoice_date, f_date)
            if m.invoice_date_due:
                ws2.write_datetime(rr, 4, m.invoice_date_due, f_date)
            else:
                ws2.write_blank(rr, 4, None, f_date)
            ws2.write_number(rr, 5, m.amount_total_signed, f_num)
            ws2.write_number(rr, 6, m.amount_total_signed - m.amount_residual_signed, f_num)
            ws2.write_number(rr, 7, m.amount_residual_signed, f_num)
            ws2.write_datetime(rr, 8, m.invoice_date, f_date)
            ws2.write(rr, 9, state_lbl.get(m.payment_state, m.payment_state or ""), f_txt)
            ws2.write(rr, 10, m.ref or m.invoice_origin or "", f_txt)
            ws2.write_datetime(rr, 14, m.invoice_date, f_date)
            rr += 1
        for row in rows:
            label = self._partner_label(row["partner"])
            for grp, m, pd, eff, bn in sorted(row["invoices"], key=lambda t: (t[3], t[1].name)):
                ws2.write(rr, 0, label, f_txt)
                ws2.write(rr, 1, grp, f_txt)
                ws2.write(rr, 2, m.name, f_txt)
                if m.invoice_date:
                    ws2.write_datetime(rr, 3, m.invoice_date, f_date)
                else:
                    ws2.write_blank(rr, 3, None, f_date)
                ws2.write_datetime(rr, 4, m.invoice_date_due, f_date)
                ws2.write_number(rr, 5, m.amount_total_signed, f_num)
                ws2.write_number(rr, 6, m.amount_total_signed - m.amount_residual_signed, f_num)
                ws2.write_number(rr, 7, m.amount_residual_signed, f_num)
                if pd:
                    ws2.write_datetime(rr, 8, pd, f_date)
                else:
                    ws2.write_blank(rr, 8, None, f_date)
                ws2.write(rr, 9, state_lbl.get(m.payment_state, m.payment_state or ""), f_txt)
                ws2.write(rr, 10, m.ref or m.invoice_origin or "", f_txt)
                write_bn_cols(rr, bn, eff)
                rr += 1
        ws2.autofilter(0, 0, max(rr - 1, 1), len(heads) - 1)

        wb.close()
        return buf.getvalue()

