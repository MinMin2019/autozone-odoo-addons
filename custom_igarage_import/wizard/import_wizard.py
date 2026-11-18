import calendar
from collections import OrderedDict, defaultdict
from datetime import date, timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

BAD_QTY = 4e9          # บั๊ก iGarage: จำนวน 4,294,967,295
DO_SENT = (2, 3)        # delivery_order_statuses: 2 รอรับ, 3 รับแล้ว (ข้าม 1 รออนุมัติ, 4 ยกเลิก)
ITEM_CANCEL = 4


def _month_range(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


class IgarageImportWizard(models.TransientModel):
    _name = "az.igarage.import.wizard"
    _description = "ดึงข้อมูลจาก iGarage / AutoPart เป็นดราฟ"

    mode = fields.Selection([
        ("transfer", "ใบโอนสาขา จากใบส่งของ (DO) iGarage"),
        ("cons_igarage", "ใบเบิกรายเดือน จาก iGarage (สาขา)"),
        ("cons_autopart", "ใบเบิกรายเดือน จาก AutoPart (ATP)"),
    ], required=True, default="transfer")
    date_from = fields.Date("ตั้งแต่วันที่", default=lambda s: fields.Date.context_today(s).replace(day=1))
    date_to = fields.Date("ถึงวันที่", default=fields.Date.context_today)
    month = fields.Char("เดือน (YYYY-MM)", default=lambda s: fields.Date.context_today(s).strftime("%Y-%m"))
    warehouse_ids = fields.Many2many("stock.warehouse", string="เฉพาะสาขา", help="เว้นว่าง = ทุกสาขาที่จับคู่ไว้")
    min_date = fields.Date("ใบโอน: ห้ามดึงก่อนวันที่", default=date(2026, 11, 5), readonly=True,
                           help="ใบโอนถึง 4 พ.ย. 2569 และใบเบิกถึง ต.ค. 2569 ลงจากการนับสต็อกแล้ว")
    state = fields.Selection([("draft", "ตั้งค่า"), ("done", "ผลการดึง")], default="draft")
    result_html = fields.Html("ผลการดึง", readonly=True, sanitize=False)
    transfer_ids = fields.Many2many("az.branch.transfer", string="ใบโอนที่สร้าง")
    consumption_ids = fields.Many2many("az.branch.consumption", string="ใบเบิกที่สร้าง")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("default_mode"):
            res["mode"] = self.env.context["default_mode"]
        return res

    # ---------------------------------------------------------------- helpers
    def _maps(self):
        M = self.env["az.igarage.warehouse.map"].search([])
        central = M.filtered("is_central")
        if not central:
            raise UserError(_("ยังไม่ได้กำหนดคลังกลาง (AZG) ในตารางจับคู่คลัง iGarage"))
        return M, central

    def _product_finder(self):
        PP = self.env["product.product"].with_context(active_test=False)
        cache = {}

        def find(sku, name):
            key = (sku or "", name or "")
            if key not in cache:
                p = PP.browse()
                if sku:
                    p = PP.search([("product_tmpl_id.az_sku", "=", sku), ("active", "=", True)], limit=1) or \
                        PP.search([("product_tmpl_id.az_sku", "=", sku)], limit=1)
                if not p and name:
                    p = PP.search([("default_code", "=", name.strip())], limit=1) or PP.search([("name", "=", name.strip())], limit=1)
                cache[key] = p if (p and p.is_storable) else False
                if p and not p.is_storable:
                    cache[key] = "nonstock"
            return cache[key]
        return find

    def _check_dates(self, d0, minimum=None):
        minimum = minimum or self.min_date
        if d0 < minimum:
            raise UserError(_("ห้ามดึงข้อมูลก่อนวันที่ %s (ช่วงก่อนหน้านี้ลงจากการนับสต็อกแล้ว)") % minimum.strftime("%d/%m/%Y"))

    def _html(self, title, created, rows_skip, unmatched, nonstock, warn):
        h = [Markup("<h4>%s</h4>") % title, Markup("<p><b>สร้างดราฟ %s ใบ</b></p>") % created]
        def block(head, items):
            if items:
                h.append(Markup("<p><b>%s</b> (%s)</p><ul>") % (head, len(items)))
                for it in items[:300]:
                    h.append(Markup("<li>%s</li>") % it)
                h.append(Markup("</ul>"))
        block("ข้าม", rows_skip)
        block("สินค้าจับคู่กับ Odoo ไม่ได้ (ไม่ได้ใส่ในดราฟ)", unmatched)
        block("สินค้าไม่ได้คุมสต็อกใน Odoo (ไม่ได้ใส่)", nonstock)
        block("ควรตรวจ", warn)
        return Markup("").join(h)

    def _done(self, html):
        self.write({"state": "done", "result_html": html})
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "new"}

    # ---------------------------------------------------------------- actions
    def action_import(self):
        self.ensure_one()
        return getattr(self, "_import_" + self.mode)()

    def _import_transfer(self):
        if not (self.date_from and self.date_to) or self.date_from > self.date_to:
            raise UserError(_("กรุณาระบุช่วงวันที่ให้ถูกต้อง"))
        self._check_dates(self.date_from)
        M, central = self._maps()
        wmap = {m.igarage_wh_id: m for m in M}
        cids = central.mapped("igarage_wh_id")
        only = set(self.warehouse_ids.ids)
        conn = self.env["az.igarage.connector"].igarage_connect()
        try:
            cur = conn.cursor()
            ph = ",".join(["%s"] * len(cids))
            cur.execute(f"""
                select o.id, o.reference, o.date, o.from_warehouse_id, o.to_warehouse_id, o.delivery_order_status_id,
                       coalesce(cs.sku,''), cs.name, i.amount_sent, i.amount_recieved, i.amount_lost
                from delivery_orders o join delivery_items i on i.delivery_order_id=o.id
                join consumables cs on cs.id=i.consumable_id
                where o.date between %s and %s and o.is_active=1 and o.delivery_order_status_id in (2,3)
                  and coalesce(i.delivery_item_status_id,0)<>{ITEM_CANCEL}
                  and (o.from_warehouse_id in ({ph}) or o.to_warehouse_id in ({ph}))
                order by o.date, o.id""", [self.date_from, self.date_to] + cids + cids)
            rows = cur.fetchall()
        finally:
            conn.close()
        dos = OrderedDict()
        for oid, ref, d, fw, tw, st, sku, name, sent, rec, lost in rows:
            dos.setdefault(ref, dict(date=d, fw=fw, tw=tw, st=st, items=[]))["items"].append((sku, name, float(sent or 0), float(rec or 0), float(lost or 0)))
        T = self.env["az.branch.transfer"]
        find = self._product_finder()
        created, skip, unmatched, nonstock, warn = T.browse(), [], set(), set(), []
        for ref, o in dos.items():
            out = o["fw"] in cids
            other = wmap.get(o["tw"] if out else o["fw"])
            hub = wmap.get(o["fw"] if out else o["tw"])
            if other and other.is_central_use:
                continue        # ส่งไป OTH/RMA = เบิกใช้ส่วนกลาง → ดึงผ่านใบเบิก H.O.
            if not other or other.is_central:
                skip.append(_("%s: คลังปลายทาง/ต้นทางใน iGarage (%s) ยังไม่ได้จับคู่กับ Odoo") % (ref, o["tw"] if out else o["fw"]))
                continue
            if only and other.warehouse_id.id not in only:
                continue
            if T.search_count([("igarage_do_ref", "=", ref), ("state", "!=", "cancel")]):
                skip.append(_("%s: ดึงมาแล้ว") % ref)
                continue
            lines = defaultdict(float)
            for sku, name, sent, rec, lost in o["items"]:
                if sent <= 0 or sent >= BAD_QTY:
                    if sent >= BAD_QTY:
                        warn.append(_("%s: %s จำนวนผิดปกติ (%s) ไม่ได้ใส่") % (ref, name, sent))
                    continue
                p = find(sku, name)
                if isinstance(p, str):  # "nonstock"
                    nonstock.add("%s %s" % (sku, name))
                    continue
                if not p:
                    unmatched.add("%s %s (%s)" % (sku or "-", name, ref))
                    continue
                lines[p.id] += sent
                if lost:
                    warn.append(_("%s: %s สาขาแจ้งของหาย %s") % (ref, name, lost))
            if not lines:
                skip.append(_("%s: ไม่มีรายการที่จับคู่ได้") % ref)
                continue
            same = T.search_count([("igarage_do_ref", "=", False), ("state", "!=", "cancel"), ("date", "=", o["date"]),
                                   ("warehouse_id", "=", other.warehouse_id.id), ("direction", "=", "out" if out else "return")])
            if same:
                warn.append(_("%s: มีใบโอนที่คีย์เองใน Odoo วันเดียวกันไปคลังเดียวกันอยู่แล้ว %s ใบ — ตรวจว่าซ้ำหรือไม่") % (ref, same))
            st = {2: "รอรับ", 3: "รับแล้ว"}.get(o["st"], str(o["st"]))
            created |= T.create({
                "direction": "out" if out else "return",
                "source_warehouse_id": hub.warehouse_id.id,
                "warehouse_id": other.warehouse_id.id,
                "date": o["date"],
                "igarage_do_ref": ref,
                "note": _("ดึงจาก iGarage %s (สถานะใน iGarage: %s)") % (ref, st),
                "line_ids": [(0, 0, {"product_id": pid, "product_uom_qty": q}) for pid, q in lines.items()],
            })
        self.transfer_ids = created
        return self._done(self._html(_("ใบโอนจาก iGarage %s – %s") % (self.date_from.strftime("%d/%m/%Y"), self.date_to.strftime("%d/%m/%Y")),
                                     len(created), skip, sorted(unmatched), sorted(nonstock), warn))

    def _cons_create(self, wh, d1, items, ref, purpose, skip, unmatched, nonstock, find):
        C = self.env["az.branch.consumption"]
        old = C.search([("import_ref", "=", ref), ("state", "!=", "cancel")])
        if old.filtered(lambda c: c.state != "draft"):
            skip.append(_("%s: ดึงเดือนนี้และยืนยันไปแล้ว — ไม่สร้างซ้ำ") % ref)
            return C.browse()
        if old:
            skip.append(_("%s: แทนที่ดราฟเดิม %s ด้วยยอดล่าสุด") % (ref, ", ".join(old.mapped("name"))))
            old.unlink()
        d0 = d1.replace(day=1)
        manual = C.search_count([("import_ref", "=", False), ("state", "!=", "cancel"), ("warehouse_id", "=", wh.id),
                                 ("date", ">=", d0), ("date", "<=", d1)])
        if manual:
            skip.append(_("%s: เตือน — มีใบเบิกที่คีย์เองใน Odoo เดือนนี้แล้ว %s ใบ ตรวจว่าซ้ำหรือไม่ (ยังสร้างดราฟให้)") % (ref, manual))
        lines = defaultdict(float)
        for sku, name, q in items:
            p = find(sku, name)
            if isinstance(p, str):  # "nonstock"
                nonstock.add("%s %s" % (sku, name))
                continue
            if not p:
                unmatched.add("%s %s (%s)" % (sku or "-", name, wh.code))
                continue
            lines[p.id] += q
        lines = {k: v for k, v in lines.items() if v > 0}
        if not lines:
            skip.append(_("%s: ไม่มียอดเบิก") % ref)
            return C.browse()
        return C.create({"warehouse_id": wh.id, "date": d1, "purpose": purpose, "import_ref": ref,
                         "note": _("ดึงจากระบบภายนอก %s") % ref,
                         "line_ids": [(0, 0, {"product_id": pid, "product_uom_qty": q}) for pid, q in lines.items()]})

    def _month_dates(self):
        if not self.month or len(self.month) != 7:
            raise UserError(_("กรุณาระบุเดือนแบบ YYYY-MM เช่น 2026-11"))
        d0, d1 = _month_range(self.month)
        self._check_dates(d0, date(2026, 11, 1))
        today = fields.Date.context_today(self)
        return d0, min(d1, today)

    def _import_cons_igarage(self):
        d0, d1 = self._month_dates()
        M, central = self._maps()
        maps = M.filtered(lambda m: m.use_for_consumption and not m.is_central)
        if self.warehouse_ids:
            maps = maps.filtered(lambda m: m.warehouse_id in self.warehouse_ids)
        cu0 = M.filtered("is_central_use")
        if self.warehouse_ids:
            cu0 = cu0.filtered(lambda m: m.warehouse_id in self.warehouse_ids)
        if not maps and not cu0:
            raise UserError(_("ไม่มีคลังที่ตั้งให้ดึงยอดเบิก"))
        ids = maps.mapped("igarage_wh_id") or [-1]
        conn = self.env["az.igarage.connector"].igarage_connect()
        try:
            cur = conn.cursor()
            ph = ",".join(["%s"] * len(ids))
            # เบิกใช้ (type 2 ที่ไม่ใช่การส่ง DO) + ย้ายเข้าห้องสี (type 4) ; ไม่รวมใบปรับ (type 3)
            cur.execute(f"""
                select sc.warehouse_id, coalesce(cs.sku,''), cs.name, sum(sc.qty_withdraw), max(sc.qty_withdraw)
                from warehouse_consumable_stock_cards sc join consumables cs on cs.id=sc.consumable_id
                where sc.warehouse_id in ({ph}) and sc.transaction_datetime >= %s and sc.transaction_datetime < %s
                  and sc.qty_withdraw > 0 and sc.qty_withdraw < {BAD_QTY}
                  and ((sc.stock_card_type_id = 2 and coalesce(sc.remark,'') not like 'ตัดออกเพื่อส่ง%%')
                       or sc.stock_card_type_id = 4)
                group by 1,2,3""", ids + [d0, date.fromordinal(_month_range(self.month)[1].toordinal() + 1)])
            rows = cur.fetchall()
            # ของฟรี/ย้ายสีเข้าห้องสีที่บันทึกรับจากผู้ขายบริษัทเอง — แจ้งให้ตรวจ
            cur.execute(f"""
                select sc.warehouse_id, cs.name, sum(sc.qty_deposit)
                from warehouse_consumable_stock_cards sc join consumables cs on cs.id=sc.consumable_id
                left join consumable_purchase_order_items pi on pi.id=sc.consumable_purchase_order_item_id
                left join warehouse_deposit_logs dl on dl.id=sc.warehouse_deposit_log_id
                left join consumable_purchase_orders po on po.id=coalesce(pi.consumable_purchase_order_id, dl.consumable_purchase_order_id)
                left join suppliers s on s.id=po.supplier_id
                where sc.warehouse_id in ({ph}) and sc.transaction_datetime >= %s and sc.transaction_datetime < %s
                  and s.name like '%%ออโต้โซน%%' group by 1,2""", ids + [d0, date.fromordinal(_month_range(self.month)[1].toordinal() + 1)])
            free = cur.fetchall()
        finally:
            conn.close()
        by = defaultdict(list)
        for w, sku, name, q, mx in rows:
            by[w].append((sku, name, float(q or 0)))
        wm = {m.igarage_wh_id: m for m in maps}
        cu = M.filtered("is_central_use")
        if self.warehouse_ids:
            cu = cu.filtered(lambda m: m.warehouse_id in self.warehouse_ids)
        if cu:
            conn = self.env["az.igarage.connector"].igarage_connect()
            try:
                cur = conn.cursor()
                cids = central.mapped("igarage_wh_id")
                ids2 = cu.mapped("igarage_wh_id")
                cur.execute(f"""
                    select o.to_warehouse_id, coalesce(cs.sku,''), cs.name, sum(i.amount_sent)
                    from delivery_orders o join delivery_items i on i.delivery_order_id=o.id join consumables cs on cs.id=i.consumable_id
                    where o.date between %s and %s and o.is_active=1 and o.delivery_order_status_id in (2,3)
                      and coalesce(i.delivery_item_status_id,0)<>{ITEM_CANCEL} and i.amount_sent < {BAD_QTY}
                      and o.from_warehouse_id in ({",".join(["%s"] * len(cids))}) and o.to_warehouse_id in ({",".join(["%s"] * len(ids2))})
                    group by 1,2,3""", [d0, _month_range(self.month)[1]] + cids + ids2)
                for w, sku, name, q in cur.fetchall():
                    by[w].append((sku, name, float(q or 0)))
            finally:
                conn.close()
            for m in cu:
                wm[m.igarage_wh_id] = m
        warn = [_("%s: %s รับจากผู้ขาย บ.ออโต้โซน %s (อาจเป็นการย้ายสีเข้าห้องสี ไม่ใช่การเบิกจริง)") % (wm[w].warehouse_id.code, n, q)
                for w, n, q in free if w in wm]
        find = self._product_finder()
        created, skip, unmatched, nonstock = self.env["az.branch.consumption"].browse(), [], set(), set()
        # หลายคลัง iGarage อาจชี้คลัง Odoo เดียวกัน → รวมก่อน
        per_wh = defaultdict(list)
        for w, items in by.items():
            per_wh[wm[w].warehouse_id].extend(items)
        for wh, items in per_wh.items():
            created |= self._cons_create(wh, d1, items, "IGARAGE:%s:%s" % (wh.code, self.month),
                                         _("เบิกใช้ตาม iGarage เดือน %s") % self.month, skip, unmatched, nonstock, find)
        self.consumption_ids = created
        return self._done(self._html(_("ใบเบิกจาก iGarage เดือน %s") % self.month, len(created), skip, sorted(unmatched), sorted(nonstock), warn))

    def _import_cons_autopart(self):
        d0, d1 = self._month_dates()
        code = self.env["ir.config_parameter"].sudo().get_param("custom_igarage_import.autopart_warehouse", "ATP")
        wh = self.env["stock.warehouse"].search([("code", "=", code)], limit=1)
        if not wh:
            raise UserError(_("ไม่พบคลัง %s สำหรับยอดเบิก AutoPart") % code)
        e0, e1 = _month_range(self.month)
        conn = self.env["az.igarage.connector"].autopart_connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT ISNULL(i.SKU,''), s.ConsumableName, SUM(s.Issue) - SUM(s.Returned)
                FROM ConsumableStockcard s JOIN ConsumableItem i ON i.ConsumableName = s.ConsumableName
                WHERE s.StockType = 'N' AND s.StockCardDate >= ? AND s.StockCardDate < ?
                GROUP BY i.SKU, s.ConsumableName
                HAVING SUM(s.Issue) - SUM(s.Returned) > 0""", e0.isoformat(), (e1 + timedelta(days=1)).isoformat())  # ไดรเวอร์ SQL Server รุ่นเก่าไม่รับพารามิเตอร์ชนิดวันที่
            rows = cur.fetchall()
        finally:
            conn.close()
        items = [(str(r[0] or "").strip(), str(r[1] or "").strip(), float(r[2] or 0)) for r in rows]
        find = self._product_finder()
        skip, unmatched, nonstock = [], set(), set()
        created = self._cons_create(wh, d1, items, "AUTOPART:%s:%s" % (wh.code, self.month),
                                    _("เบิกใช้ตาม AutoPart เดือน %s") % self.month, skip, unmatched, nonstock, find)
        self.consumption_ids = created
        return self._done(self._html(_("ใบเบิก %s จาก AutoPart เดือน %s") % (wh.code, self.month), len(created), skip, sorted(unmatched), sorted(nonstock), []))

    def action_open_created(self):
        self.ensure_one()
        if self.transfer_ids:
            return {"type": "ir.actions.act_window", "name": _("ใบโอนที่สร้าง"), "res_model": "az.branch.transfer",
                    "view_mode": "list,form", "domain": [("id", "in", self.transfer_ids.ids)]}
        return {"type": "ir.actions.act_window", "name": _("ใบเบิกที่สร้าง"), "res_model": "az.branch.consumption",
                "view_mode": "list,form", "domain": [("id", "in", self.consumption_ids.ids)]}
