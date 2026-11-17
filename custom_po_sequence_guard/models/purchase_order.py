# -*- coding: utf-8 -*-
"""เลข PO: ออกเลขอัตโนมัติรายเดือน + แก้เลขเองได้ตอนเป็น RFQ + กันเลขซ้ำ/ผิดรูปแบบ

* ตัวนับแยกรายเดือน (ir.sequence.date_range 1 ช่วง = 1 เดือน) prefix ใช้เดือนของช่วงตัวนับ
  (``%(range_year)s%(range_month)s``) ใบที่คีย์ย้อนหลัง (Order Deadline/date_order เดือนเก่า)
  จึงได้เลขของเดือนนั้น และตัวนับจะต่อจากเลขสูงสุดที่ใช้แล้วในเดือนนั้นเสมอ
  (รวมเลขที่พนักงานพิมพ์เอง) ไม่ต้องตั้งตัวนับเองทุกเดือน
* create: ถ้าตัวนับยังออกเลขที่ถูกใช้แล้ว ให้ข้ามไปเลขถัดไป (log warning)
* แก้เลข PO ได้เฉพาะสถานะ RFQ / RFQ Sent (ยืนยันแล้วแก้ไม่ได้ ทั้งหน้าจอและฝั่ง server)
  ทุกการเปลี่ยนเลขถูกบันทึกใน chatter
* ตัดช่องว่างหน้า/หลัง + แปลงเป็นตัวพิมพ์ใหญ่ก่อนบันทึก; ห้ามบันทึกเลขซ้ำ (ไม่สนตัวพิมพ์) + เตือนทันทีตอนพิมพ์
* รูปแบบเลขต้องเป็น PO + ปี ค.ศ. 4 หลัก + เดือน 2 หลัก + ลำดับ 3 หลัก เช่น PO202611123
  ยกเว้นติ๊ก "เลข PO รูปแบบพิเศษ"
"""
import calendar
import logging
import re
from datetime import date, datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

PO_NAME_RE = re.compile(r"^PO20\d{2}(0[1-9]|1[0-2])\d{3}$")
EDITABLE_STATES = ("draft", "sent")
PO_SEQ_PREFIX = "PO%(range_year)s%(range_month)s"


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    name = fields.Char(tracking=True)
    az_name_free_format = fields.Boolean(
        "เลข PO รูปแบบพิเศษ", copy=False, tracking=True,
        help="ติ๊กเมื่อต้องใช้เลขที่ไม่ตรงรูปแบบ PO+ปีเดือน+ลำดับ 3 หลัก (เช่น เลขเอกสารเก่าที่คีย์ย้อนหลัง) "
             "ระบบยังตรวจเลขซ้ำเหมือนเดิม")

    # ------------------------------------------------------------------ helpers
    @api.model
    def _az_clean_name(self, name):
        """ตัดช่องว่าง + ตัวพิมพ์ใหญ่; 'new' (พิมพ์แบบไหนก็ได้) หรือเว้นว่าง = ให้ระบบออกเลขเอง"""
        if not isinstance(name, str):
            return name
        name = name.strip().upper()
        return "New" if name in ("", "NEW") else name

    def _az_find_duplicate(self, name, exclude_ids=()):
        """คืน id ของ PO อื่นที่ใช้เลขนี้แล้ว (ไม่สนช่องว่าง/ตัวพิมพ์) หรือ False"""
        name = self._az_clean_name(name)
        if not name or name in ("New", "/"):
            return False
        self.env["purchase.order"].flush_model(["name"])
        self.env.cr.execute(
            "SELECT id FROM purchase_order WHERE lower(trim(name)) = lower(%s) AND NOT (id = ANY(%s)) LIMIT 1",
            (name, list(exclude_ids) or [0]))
        row = self.env.cr.fetchone()
        return row and row[0]

    def _az_name_used(self, name):
        return bool(self._az_find_duplicate(name))

    @api.model
    def _az_po_sequence(self, company_id):
        return self.env["ir.sequence"].sudo().search(
            [("code", "=", "purchase.order"), ("company_id", "in", [company_id, False])],
            order="company_id", limit=1)

    @api.model
    def _az_prepare_month_range(self, seq, seq_date):
        """ถ้ายังไม่มีช่วงตัวนับของเดือนนั้น ให้สร้าง (1 เดือน) โดยเริ่มต่อจากเลขสูงสุดที่ใช้แล้วในเดือนนั้น

        หลังจากนั้นตัวนับเดินเองตามปกติ เลขที่มีคนพิมพ์ใช้ไปก่อนจะถูกข้ามใน _az_next_po_name
        (ไม่ดึงตัวนับไปตามเลขสูงสุดทุกครั้ง กันเคสพิมพ์เลขผิดล่วงหน้าแล้วตัวนับกระโดดตาม)
        """
        if not seq or not seq.use_date_range:
            return
        if isinstance(seq_date, datetime):
            dt = seq_date.date()
        elif isinstance(seq_date, date):
            dt = seq_date
        else:
            dt = fields.Date.context_today(self)
        DateRange = self.env["ir.sequence.date_range"].sudo()
        if DateRange.search_count([("sequence_id", "=", seq.id), ("date_from", "<=", dt), ("date_to", ">=", dt)], limit=1):
            return
        first = dt.replace(day=1)
        last = dt.replace(day=calendar.monthrange(dt.year, dt.month)[1])
        # ไม่ให้ทับช่วงที่มีอยู่ (ถ้ามีคนสร้างช่วงไว้เอง)
        before = DateRange.search([("sequence_id", "=", seq.id), ("date_to", ">=", first), ("date_to", "<", dt)],
                                  order="date_to desc", limit=1)
        after = DateRange.search([("sequence_id", "=", seq.id), ("date_from", "<=", last), ("date_from", ">", dt)],
                                 order="date_from asc", limit=1)
        if before:
            first = fields.Date.add(before.date_to, days=1)
        if after:
            last = fields.Date.subtract(after.date_from, days=1)
        prefix, suffix = seq.with_context(ir_sequence_date_range=first)._get_prefix_suffix()
        self.env["purchase.order"].flush_model(["name"])
        self.env.cr.execute(
            "SELECT max(substring(trim(name) FROM %s)::int) FROM purchase_order WHERE trim(name) ~ %s",
            (r"^%s(\d+)%s$" % (re.escape(prefix), re.escape(suffix)),
             r"^%s\d{%d}%s$" % (re.escape(prefix), seq.padding, re.escape(suffix))))
        max_used = self.env.cr.fetchone()[0] or 0
        _logger.info("PO sequence: new range %s..%s starts at %s (highest used %s%0*d)",
                     first, last, max_used + 1, prefix, seq.padding, max_used)
        DateRange.create({"sequence_id": seq.id, "date_from": first, "date_to": last,
                          "number_next_actual": max_used + 1})

    @api.model
    def _az_setup_po_sequence(self):
        """เรียกตอนติดตั้ง/อัปเกรดโมดูล: เปิดตัวนับรายเดือนให้ sequence ของ PO"""
        for seq in self.env["ir.sequence"].sudo().search([("code", "=", "purchase.order")]):
            vals = {}
            if not seq.use_date_range:
                vals["use_date_range"] = True
            if seq.prefix in ("PO%(year)s%(month)s", "PO"):
                vals["prefix"] = PO_SEQ_PREFIX
            if vals:
                _logger.info("Setup PO sequence %s: %s", seq.id, vals)
                seq.write(vals)

    # ------------------------------------------------------------------ ORM
    @api.model
    def _az_next_po_name(self, company_id, date_order):
        """เหมือน core purchase.order.create แต่ตัวนับรายเดือน + ข้ามเลขที่ถูกใช้แล้ว"""
        self_comp = self.with_company(company_id)
        seq_date = None
        if date_order:
            seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(date_order))
        self_comp._az_prepare_month_range(self_comp._az_po_sequence(company_id), seq_date)
        name = False
        for _i in range(500):
            name = self_comp.env["ir.sequence"].next_by_code("purchase.order", sequence_date=seq_date)
            if not name or not self._az_name_used(name):
                break
            _logger.warning("PO sequence gave already-used number %s -> skip to next", name)
        return name or "/"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "name" in vals:
                vals["name"] = self._az_clean_name(vals["name"])
            if vals.get("name", "New") not in ("New", False):
                continue
            company_id = vals.get("company_id", self.default_get(["company_id"])["company_id"])
            vals["name"] = self._az_next_po_name(company_id, vals.get("date_order"))
        return super().create(vals_list)

    def write(self, vals):
        if "name" in vals:
            vals["name"] = self._az_clean_name(vals["name"])
            if not self.env.context.get("az_allow_po_rename"):
                locked = self.filtered(lambda o: o.state not in EDITABLE_STATES and o.name != vals["name"])
                if locked:
                    raise UserError(_("แก้เลข PO ได้เฉพาะตอนเป็น RFQ (ยังไม่ยืนยัน) เท่านั้น: %s")
                                    % ", ".join(locked.mapped("name")))
            if vals["name"] in ("New", False):
                # ลบเลขออก/พิมพ์ New = ให้ระบบออกเลขใหม่ (ตามเดือนของวันที่สั่งซื้อ)
                rest = {k: v for k, v in vals.items() if k != "name"}
                for order in self:
                    name = self._az_next_po_name(order.company_id.id, rest.get("date_order") or order.date_order)
                    super(PurchaseOrder, order).write(dict(rest, name=name))
                return True
        return super().write(vals)

    # ------------------------------------------------------------------ checks
    @api.onchange("name")
    def _onchange_az_name_duplicate(self):
        for order in self:
            name = self._az_clean_name(order.name)
            if not name or name in ("New", "/"):
                continue
            dup = self._az_find_duplicate(name, exclude_ids=[order._origin.id] if order._origin.id else [])
            if dup:
                other = self.browse(dup).sudo()
                return {"warning": {
                    "title": _("เลข PO ซ้ำ"),
                    "message": _("เลข %s มีใช้แล้วในใบ %s (สถานะ %s) บันทึกไม่ได้ กรุณาใช้เลขอื่น")
                               % (name, other.name, dict(other._fields["state"]._description_selection(self.env)).get(other.state)),
                }}

    @api.constrains("name")
    def _check_az_unique_name(self):
        for order in self:
            if not order.name or order.name in ("New", "/"):
                continue
            dup = self._az_find_duplicate(order.name, exclude_ids=[order.id])
            if dup:
                other = self.browse(dup).sudo()
                raise ValidationError(_("เลข PO %s ซ้ำกับใบ %s ที่มีอยู่แล้ว บันทึกไม่ได้ กรุณาใช้เลขอื่น")
                                      % (order.name, other.name))

    @api.constrains("name", "az_name_free_format")
    def _check_az_name_format(self):
        for order in self:
            if order.az_name_free_format or not order.name or order.name in ("New", "/"):
                continue
            if not PO_NAME_RE.match(order.name):
                raise ValidationError(_(
                    "เลข PO \"%s\" ไม่ถูกรูปแบบ\n"
                    "ต้องเป็น PO + ปี ค.ศ. 4 หลัก + เดือน 2 หลัก + ลำดับ 3 หลัก เช่น PO202611123\n"
                    "(ปีต้องเป็น ค.ศ. ไม่ใช่ พ.ศ.)\n"
                    "ถ้าจำเป็นต้องใช้เลขแบบอื่น ให้ติ๊ก \"เลข PO รูปแบบพิเศษ\"") % order.name)
