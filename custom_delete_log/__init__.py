from . import models
from . import controllers

# โมเดลตั้งต้นที่เปิดเก็บ log ตอนติดตั้ง — เพิ่ม/ลดภายหลังได้ที่เมนู
# Settings > Technical > Deletion Log > Tracked Models
DEFAULT_TRACKED_MODELS = [
    "crm.lead",
    "sale.order",
    "purchase.order",
    "account.move",
    "res.partner",
]


def post_init_hook(env):
    Rule = env["record.delete.rule"]
    IrModel = env["ir.model"]
    for model_name in DEFAULT_TRACKED_MODELS:
        if model_name not in env:
            continue
        model = IrModel._get(model_name)
        if model and not Rule.with_context(active_test=False).search(
            [("model_id", "=", model.id)], limit=1
        ):
            Rule.create({"model_id": model.id})
