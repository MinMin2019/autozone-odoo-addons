from markupsafe import Markup, escape

from odoo import api, models

# ฟิลด์ราคาผู้ขายที่บันทึกประวัติลงแชทของสินค้า — แท็บ Purchase จัดซื้อแก้เองได้
# โดยไม่ต้องอนุมัติ (1.2.2) จึงต้องมีร่องรอยว่าใครเปลี่ยนอะไร
TRACKED = ("partner_id", "price", "currency_id", "min_qty", "discount",
           "date_start", "date_end", "product_id")


class ProductSupplierinfo(models.Model):
    _inherit = "product.supplierinfo"

    def _mda_fmt(self, fname):
        val = self[fname]
        field = self._fields[fname]
        if field.type == "many2one":
            return val.display_name or "-"
        if field.type == "float":
            return "{:,.2f}".format(val)
        return str(val) if val else "-"

    def _mda_log(self, lines_by_tmpl):
        author = self.env.user.partner_id
        email_from = (self.env.user.email_formatted
                      or self.env.company.email_formatted or "odoo@localhost")
        for tmpl, lines in lines_by_tmpl.items():
            body = Markup("ราคาผู้ขาย (แก้โดย %s):<br/>") % self.env.user.name
            body += Markup("<br/>").join(escape(line) for line in lines)
            tmpl.sudo().message_post(
                body=body, author_id=author.id, email_from=email_from)

    def _mda_label(self):
        return self.partner_id.display_name or "-"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        logs = {}
        for rec in records.filtered("product_tmpl_id"):
            logs.setdefault(rec.product_tmpl_id, []).append(
                "+ เพิ่ม %s ราคา %s %s (ขั้นต่ำ %s)" % (
                    rec._mda_label(), rec._mda_fmt("price"),
                    rec._mda_fmt("currency_id"), rec._mda_fmt("min_qty")))
        records._mda_log(logs)
        return records

    def write(self, vals):
        fnames = [f for f in TRACKED if f in vals]
        before = {rec.id: {f: rec._mda_fmt(f) for f in fnames} for rec in self} if fnames else {}
        res = super().write(vals)
        if fnames:
            logs = {}
            for rec in self.filtered("product_tmpl_id"):
                changes = [
                    "%s: %s → %s" % (rec._fields[f].string, before[rec.id][f], rec._mda_fmt(f))
                    for f in fnames if before[rec.id][f] != rec._mda_fmt(f)]
                if changes:
                    logs.setdefault(rec.product_tmpl_id, []).append(
                        "• %s — %s" % (rec._mda_label(), ", ".join(changes)))
            self._mda_log(logs)
        return res

    def unlink(self):
        logs = {}
        for rec in self.filtered("product_tmpl_id"):
            logs.setdefault(rec.product_tmpl_id, []).append(
                "− ลบ %s ราคา %s" % (rec._mda_label(), rec._mda_fmt("price")))
        res = super().unlink()
        self._mda_log(logs)
        return res
