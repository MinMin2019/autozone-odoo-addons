import csv
import logging
import os
import re

_logger = logging.getLogger(__name__)

# ชื่อโมดูลจริง (= ชื่อโฟลเดอร์) ดึงอัตโนมัติ ไม่ผูกกับชื่อ hardcode
# __name__ = 'odoo.addons.<module>.hooks'
MODULE = __name__.split(".")[-2]


# ---------------------------------------------------------------- domain parser
def _split_top_commas(text):
    """แยกด้วย ',' ที่อยู่นอกวงเล็บเท่านั้น"""
    parts, depth, buf = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def parse_domain_hint(hint):
    """แปลง hint แบบง่ายเป็น Odoo domain string; ถ้าแปลงไม่ได้คืน None (ให้ admin เติมเอง)
    รองรับ: field=value | field in (a,b) | field>0 | field=True/False | AND ด้วย comma"""
    if not hint:
        return None
    hint = hint.strip()
    # ตัดคำอธิบายไทยในวงเล็บท้าย เช่น "customer_rank>0 (ถ้าจะแยก...)"
    hint = re.sub(r"\s*\([^)]*[฀-๿][^)]*\)\s*$", "", hint).strip()
    if not hint:
        return None
    conds = []
    for part in _split_top_commas(hint):
        m = re.match(r"^([a-z_]+)\s+in\s+\(([^)]*)\)$", part)
        if m:
            vals = [v.strip() for v in m.group(2).split(",") if v.strip()]
            conds.append([m.group(1), "in", vals])
            continue
        m = re.match(r"^([a-z_]+)\s*=\s*(True|False)$", part)
        if m:
            conds.append([m.group(1), "=", m.group(2) == "True"])
            continue
        m = re.match(r"^([a-z_]+)\s*!=\s*(True|False)$", part)
        if m:
            conds.append([m.group(1), "!=", m.group(2) == "True"])
            continue
        m = re.match(r"^([a-z_]+)\s*>\s*(\d+)$", part)
        if m:
            conds.append([m.group(1), ">", int(m.group(2))])
            continue
        m = re.match(r"^([a-z_]+)\s*=\s*([A-Za-z0-9_ ]+)$", part)
        if m:
            conds.append([m.group(1), "=", m.group(2).strip()])
            continue
        return None  # เจอ pattern ที่ไม่รองรับ -> ยกเลิกทั้งบรรทัด
    if not conds:
        return None
    return repr(conds)


def _resolve_model(env, raw):
    """ดึง model name ตัวแรกที่ valid จากเซลล์ CSV; คืน (ir.model record | None, technical | None)"""
    raw = (raw or "").strip()
    if not raw or raw.startswith("("):
        return None, None
    token = raw.split("/")[0].strip().split()[0].strip()
    if not re.match(r"^[a-z][a-z0-9_.]+$", token):
        return None, None
    model = env["ir.model"].search([("model", "=", token)], limit=1)
    return (model or None), token


def _csv_path(filename="master_matrix.csv", module_name=MODULE):
    try:
        from odoo.modules.module import get_module_resource
        p = get_module_resource(module_name, "data", filename)
        if p:
            return p
    except Exception:  # noqa: BLE001
        pass
    from odoo.modules.module import get_module_path
    base = get_module_path(module_name)
    if not base:
        return None
    return os.path.join(base, "data", filename)


# โมเดลสนับสนุนที่ Foundation จะเปิด read ให้ (best-effort; ข้ามตัวที่ไม่ได้ติดตั้ง)
FOUNDATION_READ_MODELS = [
    # accounting plumbing
    "account.journal", "account.account", "account.account.tag", "account.root",
    "account.tax", "account.tax.group", "account.payment.term",
    "account.payment.method", "account.payment.method.line",
    "account.fiscal.position", "account.incoterms", "account.journal.group",
    "account.analytic.account", "account.analytic.plan",
    # currency / bank
    "res.currency", "res.currency.rate", "res.bank", "res.partner.bank",
    "res.country", "res.country.state",
    # units / products
    "uom.uom", "uom.category", "product.category", "product.pricelist",
]


def seed_foundation(env):
    """เติม ir.model.access (read) ให้ Foundation group; idempotent + ข้ามโมเดลที่ไม่มี"""
    group = env.ref("%s.group_arb_foundation" % MODULE, raise_if_not_found=False)
    if not group:
        return 0
    Access = env["ir.model.access"]
    n = 0
    for model_name in FOUNDATION_READ_MODELS:
        model = env["ir.model"].search([("model", "=", model_name)], limit=1)
        if not model:
            continue
        key = "foundation|read|%s" % model_name
        vals = {
            "name": "arb_foundation_%s" % model_name.replace(".", "_"),
            "model_id": model.id,
            "group_id": group.id,
            "perm_read": 1, "perm_write": 0, "perm_create": 0, "perm_unlink": 0,
            "arb_generated": True, "arb_key": key,
        }
        rec = Access.search([("arb_key", "=", key)], limit=1)
        if rec:
            rec.write(vals)
        else:
            Access.create(vals)
            n += 1
    _logger.info("Access Role Builder: foundation reads created=%s", n)
    return n


def seed_custom_catalog(env):
    """seed catalog entries ที่ชี้ไป action ของ custom module (data/custom_catalog.csv)
    ข้าม action ที่ไม่พบ (โมดูลยังไม่ติดตั้ง) โดยอัตโนมัติ"""
    path = _csv_path("custom_catalog.csv")
    if not path or not os.path.exists(path):
        return 0
    Catalog = env["access.catalog"]
    n = 0
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("Name") or "").strip()
            xmlid = (row.get("ActionXMLID") or "").strip()
            if not name or not xmlid:
                continue
            action = env.ref(xmlid, raise_if_not_found=False)
            if not action:
                continue  # โมดูลต้นทางยังไม่ติดตั้ง -> ข้าม
            model = env["ir.model"].search([("model", "=", action.res_model)], limit=1)
            app = (row.get("App") or "").strip()
            section = (row.get("Section") or "").strip()
            # extra read models (comma-separated) -> resolve, skip missing
            extra_ids = []
            for mn in (row.get("ExtraRead") or "").split(","):
                mn = mn.strip()
                if not mn:
                    continue
                em = env["ir.model"].search([("model", "=", mn)], limit=1)
                if em:
                    extra_ids.append(em.id)
            vals = {
                "app": app, "section": section, "name": name,
                "action_id": action.id,
                "model_id": model.id if model else False,
                "model_name": action.res_model or False,
                "default_level": (row.get("Level") or "read").strip(),
                "needs_rule": (row.get("NeedsRule") or "").strip().upper().startswith("Y"),
                "domain": (row.get("Domain") or "").strip() or False,
                "needs_review": not bool(model),
                "extra_read_model_ids": [(6, 0, extra_ids)],
            }
            existing = Catalog.with_context(active_test=False).search([
                ("app", "=", app), ("section", "=", section), ("name", "=", name),
            ], limit=1)
            if existing:
                existing.write(vals)
            else:
                Catalog.create(vals)
                n += 1
    _logger.info("Access Role Builder: seed custom catalog — created=%s", n)
    return n


# ------------------------------------------------------------------- entrypoint
def post_init_hook(env):
    """seed access.catalog + custom catalog + foundation (idempotent)"""
    seed_catalog(env)
    seed_custom_catalog(env)
    seed_foundation(env)


def seed_catalog(env):
    path = _csv_path()
    if not path or not os.path.exists(path):
        _logger.warning("Access Role Builder: ไม่พบ master_matrix.csv ที่ %s", path)
        return 0

    Catalog = env["access.catalog"]
    created = updated = 0
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            app = (row.get("App") or "").strip()
            section = (row.get("Main") or "").strip()
            name = (row.get("Sub (เมนู)") or row.get("Sub") or "").strip()
            if not name:
                continue
            model_cell = row.get("Model (โมเดลจริง)") or row.get("Model") or ""
            model, technical = _resolve_model(env, model_cell)
            hint = (row.get("Rule domain hint") or "").strip()
            needs_rule = (row.get("ต้องใช้ ir.rule?") or "").strip().upper().startswith("Y")
            note = (row.get("หมายเหตุ") or "").strip()

            domain = parse_domain_hint(hint) if needs_rule else None
            needs_review = bool(model_cell.strip()) and model is None

            vals = {
                "app": app,
                "section": section,
                "name": name,
                "model_id": model.id if model else False,
                "model_name": technical or (model_cell.strip() or False),
                "needs_rule": needs_rule,
                "domain": domain or False,
                "domain_hint": hint or False,
                "note": note or False,
                "needs_review": needs_review,
            }
            existing = Catalog.with_context(active_test=False).search([
                ("app", "=", app), ("section", "=", section), ("name", "=", name),
            ], limit=1)
            if existing:
                existing.write(vals)
                updated += 1
            else:
                Catalog.create(vals)
                created += 1

    _logger.info("Access Role Builder: seed catalog — created=%s updated=%s", created, updated)
    return created + updated
