"""Expose the classification fields in the analysis reports.

sale / purchase / invoice analysis are SQL views: the column is added to the
SELECT (and GROUP BY when the view aggregates). Stock quants and valuation
layers are regular tables: a stored related field makes them groupable.
"""
from odoo import fields, models
from odoo.tools import SQL

from .product_template import TONES, WORK_STAGES, WORK_TYPES

M2O = [
    ("az_brand_id", "az.product.brand", "แบรนด์"),
    ("az_subtype_id", "az.product.subtype", "ประเภทย่อย"),
    ("az_owner_id", "az.product.owner", "เจ้าของสินค้า"),
    ("az_part_id", "az.car.part", "ชิ้นส่วน"),
    ("az_car_make_id", "az.car.make", "ยี่ห้อรถ"),
    ("az_car_model_id", "az.car.model", "รุ่นรถ"),
]
SEL = [
    ("az_tone", TONES, "จำนวนโทนสี"),
    ("az_work_type", WORK_TYPES, "ประเภทงาน"),
    ("az_work_stage", WORK_STAGES, "ขั้นตอนงาน"),
]
FNAMES = [f for f, *_ in M2O] + [f for f, *_ in SEL]


def _report_fields():
    res = {f: fields.Many2one(model, label, readonly=True) for f, model, label in M2O}
    res.update({f: fields.Selection(sel, label, readonly=True) for f, sel, label in SEL})
    return res


def _related_fields(path):
    res = {f: fields.Many2one(model, label, related=f"{path}.{f}", store=True, index=True)
           for f, model, label in M2O}
    res.update({f: fields.Selection(sel, label, related=f"{path}.{f}", store=True, index=True)
                for f, sel, label in SEL})
    return res


def _columns(alias):
    return SQL(", ".join(f"{alias}.{f} AS {f}" for f in FNAMES))


def _group_cols(alias):
    return SQL(", ".join(f"{alias}.{f}" for f in FNAMES))


# The same 9 field definitions are injected into each class namespace below
# (a class body namespace is a plain dict, so locals().update() is reliable here).
class SaleReport(models.Model):
    _inherit = "sale.report"
    locals().update(_report_fields())

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res.update({f: f"t.{f}" for f in FNAMES})
        return res

    def _group_by_sale(self):
        return super()._group_by_sale() + ", " + ", ".join(f"t.{f}" for f in FNAMES)


class PurchaseReport(models.Model):
    _inherit = "purchase.report"
    locals().update(_report_fields())

    def _select(self):
        return SQL("%s, %s", super()._select(), _columns("t"))

    def _group_by(self):
        return SQL("%s, %s", super()._group_by(), _group_cols("t"))


class AccountInvoiceReport(models.Model):
    _inherit = "account.invoice.report"
    locals().update(_report_fields())

    def _select(self):
        return SQL("%s, %s", super()._select(), _columns("template"))


class StockQuant(models.Model):
    _inherit = "stock.quant"
    locals().update(_related_fields("product_id.product_tmpl_id"))


class StockValuationLayer(models.Model):
    _inherit = "stock.valuation.layer"
    locals().update(_related_fields("product_id.product_tmpl_id"))
