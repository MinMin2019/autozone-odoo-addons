from . import models
from . import wizard

# รหัสคลังใน iGarage (warehouses.id) -> code คลังใน Odoo ; ตรวจจาก iGarage 17 พ.ย. 2569
DEFAULT_MAP = [
    (13, "คลังวัสดุสิ้นเปลือง AZG", "H.O.", True, False),
    (81, "AHC", "AHC", False, True), (75, "AKT", "AKT", False, True), (71, "AMU", "AMU", False, True),
    (26, "BHA", "BHA", False, True), (121, "BPA", "BPA", False, True), (85, "BPD", "BPD", False, True),
    (28, "BPH", "BPH", False, True), (72, "HTR", "HTR", False, True), (105, "IAT", "IAT", False, True),
    (126, "ICR", "ICR", False, True), (88, "IKL", "IKL", False, True), (91, "IKM", "IKM", False, True),
    (94, "IKR", "IKR", False, True), (118, "ISK", "ISK", False, True), (115, "ITP", "ITP", False, True),
    (78, "LPA", "LPA", False, True), (125, "TEV", "TEV", False, True), (47, "TIY", "TIY", False, True),
    (62, "TMC", "TMC", False, True), (24, "TPL", "TPL", False, True), (109, "VWT", "VWT", False, True),
    (33, "คลังวัสดุ ATP(โรงงานเช่า)", "ATP", False, False), (40, "คลังวัสดุ ATP(โรงงานเก่า)", "ATP", False, False),
    (8, "ATZ-วัสดุสิ้นเปลือง", "ATZ", False, True), (45, "ATZ-ซ่อมรถยนต์(วัสดุสิ้นเปลือง)", "ATZ", False, True),
]
CENTRAL_USE = [(34, "คลังวัสดุ OTH"), (41, "คลังวัสดุ RMA")]      # ส่งไปแล้ว = ส่วนกลางตัดใช้ (เบิก H.O.)


def post_init_hook(env):
    W = env["stock.warehouse"].with_context(active_test=False)
    M = env["az.igarage.warehouse.map"].with_context(active_test=False)
    for wid, name, code, central, cons in DEFAULT_MAP:
        wh = W.search([("code", "=", code)], limit=1)
        if wh and not M.search_count([("igarage_wh_id", "=", wid)]):
            M.create({"igarage_wh_id": wid, "name": name, "warehouse_id": wh.id, "is_central": central, "use_for_consumption": cons})
    ho = W.search([("code", "=", "H.O.")], limit=1)
    for wid, name in CENTRAL_USE:
        if ho and not M.search_count([("igarage_wh_id", "=", wid)]):
            M.create({"igarage_wh_id": wid, "name": name, "warehouse_id": ho.id, "is_central_use": True, "use_for_consumption": False})
