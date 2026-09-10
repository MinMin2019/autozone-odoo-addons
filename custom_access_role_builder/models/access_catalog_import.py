from odoo import _, fields, models


class AccessCatalogImport(models.TransientModel):
    """Wizard: pick an app (root menu) and auto-generate catalog entries from its menu tree."""
    _name = "access.catalog.import"
    _description = "Import Catalog from App Menu"

    menu_id = fields.Many2one(
        "ir.ui.menu", string="App (root menu)", required=True,
        domain=[("parent_id", "=", False)],
        help="Top-level app menu to decompose into catalog entries",
    )
    overwrite = fields.Boolean(
        string="Update existing entries", default=True,
        help="If a catalog entry with the same app/section/name exists, update it",
    )
    include_no_action = fields.Boolean(
        string="Skip menus without a window action", default=True,
    )

    def action_import(self):
        self.ensure_one()
        root = self.menu_id
        Catalog = self.env["access.catalog"]
        IrModel = self.env["ir.model"]
        created = updated = 0

        def _walk(menu, path):
            """path = breadcrumb ของชื่อเมนูจาก root ลงมาถึง menu ปัจจุบัน (รวม app)"""
            nonlocal created, updated
            for child in menu.child_id:
                act = child.action
                vals = False
                if act and act._name == "ir.actions.act_window" and act.res_model:
                    model = IrModel.search([("model", "=", act.res_model)], limit=1)
                    dom = act.domain if isinstance(act.domain, str) else False
                    vals = {
                        "action_id": act.id,
                        "client_action_id": False,
                        "model_id": model.id if model else False,
                        "model_name": act.res_model,
                        "domain": dom or False,
                        "needs_review": not bool(model),
                    }
                elif act and act._name == "ir.actions.client":
                    # client action (เช่น account report ของ Enterprise) — ไม่มี act_window
                    # ส่วนใหญ่ไม่มี res_model → ให้ admin เติม Data Model เอง (needs_review)
                    model = IrModel.search(
                        [("model", "=", act.res_model)], limit=1) if act.res_model else IrModel
                    vals = {
                        "action_id": False,
                        "client_action_id": act.id,
                        "model_id": model.id if model else False,
                        "model_name": act.res_model or False,
                        "needs_review": not bool(model),
                    }
                if vals:
                    # Section = หมวดชั้นแรกใต้แอปเสมอ (Customers/Vendors/Accounting/
                    # Reporting/Configuration) — ห้ามใช้ parent ติดตัว เพราะหมวดย่อยของ
                    # Configuration ชื่อ "Accounting" จะปนกับหมวด Accounting ตัวจริง
                    section = path[1] if len(path) > 1 else root.name
                    vals.update({
                        "app": root.name,
                        "section": section,
                        "menu_path": " / ".join(path),
                        "name": child.name,
                    })
                    # จับคู่ด้วย menu_path ก่อน (ระบุตำแหน่งเมนูแม่นกว่า และไม่แตกซ้ำ
                    # เมื่อสูตรตั้งชื่อ section เปลี่ยน) — fallback เป็น section+name
                    # สำหรับ entry จาก CSV ที่ยังไม่เคยมี menu_path
                    existing = Catalog.with_context(active_test=False).search([
                        ("app", "=", root.name),
                        ("menu_path", "=", vals["menu_path"]),
                        ("name", "=", child.name),
                    ], limit=1) or Catalog.with_context(active_test=False).search([
                        ("app", "=", root.name),
                        ("section", "=", section),
                        ("name", "=", child.name),
                    ], limit=1)
                    if existing:
                        if self.overwrite:
                            # entry เดิมที่ admin คัด domain ไว้ (needs_rule/domain) คือ source
                            # of truth — ถ้า action ที่ import มาไม่มี domain ห้ามล้างทิ้ง
                            # และห้ามสลับโมเดล (เคยทำ Vendors/Payments เสีย scope ทั้งเส้น)
                            if (existing.domain or existing.needs_rule) and not vals.get("domain"):
                                vals = {"menu_path": vals["menu_path"], "section": section}
                            elif existing.needs_rule and existing.domain:
                                # domain ของ action มาตรฐานมักกว้างกว่า (เช่น Bills =
                                # in_invoice+in_refund) — คง domain คัดสรรไว้ รับแค่ action/path
                                vals.pop("domain", None)
                                vals.pop("model_id", None)
                                vals.pop("model_name", None)
                            existing.write(vals)
                            updated += 1
                    else:
                        Catalog.create(vals)
                        created += 1
                # recurse; extend the breadcrumb with this menu's name
                _walk(child, path + [child.name])

        _walk(root, [root.name])

        return {
            "type": "ir.actions.act_window",
            "name": _("Imported Catalog: %s") % root.name,
            "res_model": "access.catalog",
            "view_mode": "list,form",
            "domain": [("app", "=", root.name)],
            "context": {"search_default_group_section": 1},
        }
