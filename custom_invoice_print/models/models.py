from odoo import models, fields, api
from odoo.tools import float_round


# ---------------------------------------------------------
# ส่วนที่ 0: เพิ่มรูปลายเซ็นให้ผู้ใช้ (สำหรับช่อง "ผู้อนุมัติ" ในใบกำกับ)
# ---------------------------------------------------------
class ResUsers(models.Model):
    _inherit = "res.users"

    # รูปลายเซ็นของผู้ใช้ ใช้แสดงในช่อง "ผู้อนุมัติ" ของรายงาน
    # โดยจะดึงตามผู้ใช้ที่กดสั่งพิมพ์
    x_sign_image = fields.Binary(string="ลายเซ็น (สำหรับใบกำกับ)", attachment=True)

    # เปิดให้ผู้ใช้แก้ไขลายเซ็นของตัวเองได้ผ่านหน้า Preferences
    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["x_sign_image"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["x_sign_image"]


# ---------------------------------------------------------
# ส่วนที่ 1: แก้ไข Sale Order Line (เพื่อส่งค่าไป Invoice)
# ---------------------------------------------------------
# Default Analytic ที่หัวบิล Sale Order
class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    # 1. เปลี่ยนเป็น Json เพื่อเก็บข้อมูลแบบ Widget
    x_analytic_distribution = fields.Json(string="Analytic Distribution")

    # 2. เพิ่ม Field นี้เพื่อให้ Widget ทำงานได้สมบูรณ์ (ตัวกำหนดทศนิยม)
    analytic_precision = fields.Integer(
        store=False,
        default=lambda self: self.env["decimal.precision"].precision_get(
            "Percentage Analytic"
        ),
    )

    # 3. เมื่อเปลี่ยนค่าที่หัวบิล -> ส่งไปอัปเดตทุกบรรทัดสินค้า
    @api.onchange("x_analytic_distribution")
    def _onchange_x_analytic_distribution(self):
        for line in self.order_line:
            # ส่งค่า JSON ไปตรงๆ ได้เลย
            line.analytic_distribution = self.x_analytic_distribution
            
    # 4. ดักจับตอนสร้าง Invoice เพื่อส่งค่า Customer Reference ไปด้วย (ถ้ามี)
    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        ref = self.client_order_ref or ''

        if ref.lower().startswith('do'):
            invoice_vals['x_do_reference'] = ref
            invoice_vals['x_po_reference'] = False
        elif ref.lower().startswith('po'):
            invoice_vals['x_po_reference'] = ref
            invoice_vals['x_do_reference'] = False

        return invoice_vals


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Field ใน Sale Line
    x_custom_name = fields.Char(string="รายละเอียด")

    def _prepare_invoice_line(self, **optional_values):
        res = super(SaleOrderLine, self)._prepare_invoice_line(**optional_values)
        res["x_custom_name"] = self.x_custom_name
        return res

    # 4. ดักจับตอนเพิ่มสินค้าใหม่ ให้ดึงค่าจากหัวบิลมาใส่
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'order_id' in vals:
                order = self.env['sale.order'].browse(vals['order_id'])
                # ถ้าหัวบิลมีค่า และบรรทัดสินค้ายังไม่มี -> ให้ใช้ของหัวบิล
                if order.x_analytic_distribution and not vals.get('analytic_distribution'):
                    vals['analytic_distribution'] = order.x_analytic_distribution
        
        return super(SaleOrderLine, self).create(vals_list)


# ---------------------------------------------------------
# ส่วนที่ 2: แก้ไข Account Move Line (รายการสินค้าใน Invoice)
# ---------------------------------------------------------
class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # ต้องประกาศ Field นี้ที่ฝั่ง Invoice Line ด้วย เพื่อให้มี "ที่รับของ"
    # จากที่ Sale Order ส่งมาให้
    x_custom_name = fields.Char(string="รายละเอียด")
    x_custom_name_long = fields.Text(string="รายละเอียดเต็ม")
    
    def action_open_long_desc_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "รายละเอียดเต็ม",
            "res_model": "account.move.line.long.desc.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_move_line_id": self.id,
                "default_x_custom_name_long": self.x_custom_name_long or "",
            },
        }

# ---------------------------------------------------------
# ส่วนที่ 3: แก้ไข Account Move (หัวบิล Invoice)
# ---------------------------------------------------------
class AccountMove(models.Model):
    _inherit = "account.move"

    # เหตุผลการลดหนี้ (สำหรับใบลดหนี้) — wizard "Credit Note" จะ copy ค่าจากช่อง
    # "Reason displayed on Credit Note" มาใส่ให้อัตโนมัติ (ดู AccountMoveReversal ด้านล่าง)
    # เพราะ Odoo เดิมเอา reason ไปต่อรวมกับ ref เป็น "Reversal of: ..." ใช้พิมพ์ตรง ๆ ไม่ได้
    x_cn_reason = fields.Char(string="เหตุผลการลดหนี้", copy=False)

    # วันที่ใบกำกับภาษีเดิม (ดึงจากใบกำกับที่ถูกลดหนี้)
    x_original_invoice_date = fields.Date(
        string="วันที่ใบกำกับภาษีเดิม",
        related="reversed_entry_id.invoice_date",
    )

    # 1. เพิ่ม Field เลขที่ใบสั่งซื้อ (PO Reference)
    x_po_reference = fields.Char(string="PO No.", help="เลขที่ใบสั่งซื้อจากลูกค้า")
    x_do_reference = fields.Char(string="DO No.", help="เลขที่ใบรับสินค้าจากลูกค้า")

    x_job_reference = fields.Char(string="Job No.", help="เลขที่งานซ่อม")
    x_brand_reference = fields.Char(string="Brand", help="ยี่ห้อ")
    x_car_reg_reference = fields.Char(string="Car Registration", help="ทะเบียนรถ")
    x_claim_reference = fields.Char(string="Claim", help="เลขที่เคลม")
    x_policy_reference = fields.Char(string="Policy", help="เลขที่กรมธรรม์")
    
    create_date_only = fields.Date(
        string="Created Date",
        compute="_compute_create_date_only",
        store=False  # ไม่เก็บในฐานข้อมูล คำนวณทุกครั้ง
    )
    
    
    # 2. ฟังก์ชันแปลงเงินเป็นภาษาไทย (Baht Text)
    def _compute_create_date_only(self):
        for record in self:
            if record.create_date:
                # แปลง datetime เป็น date (ตัดเวลาทิ้ง)
                record.create_date_only = record.create_date.date()
            else:
                record.create_date_only = False
    
    def get_report_pages(self, per_first=33, per_cont=33, per_last=20, per_single=20):
        """แบ่งบรรทัดใบกำกับออกเป็นหน้า ๆ สำหรับรายงาน 5 ใบ (deterministic pagination)

        **ทุกหน้าพิมพ์หัวบิล** (บัญชีขอ 2026-08-04) — ความจุเลยเหลือ 2 โครง
        (วัดจริงจากฟอร์ม A4 — หน้าเปล่าจุ 46 แถว, หัวบิลกิน 13 แถว, footer กิน 13 แถว):
          per_single = หน้าเดียวจบ  (หัวบิล + รายการ + ยอดรวม/ลายเซ็น)      = 20  (= 46 - 13 - 13)
          per_first  = หน้าแรกหลายหน้า (หัวบิล + รายการ, ไม่มี footer)        = 33  (= 46 - 13)
          per_cont   = หน้ากลาง (หัวบิล + รายการ, ไม่มี footer)               = 33  (= per_first)
          per_last   = หน้าสุดท้าย (หัวบิล + รายการ + ยอดรวม/ลายเซ็น)        = 20  (= per_single)

        หน่วยนับคือ "อะตอม" สูง 1 แถวเท่ากันหมด:
          - รายการปกติ/section/note = 1 อะตอม
          - รายการที่มี "รายละเอียดเต็ม" (x_custom_name_long) = 1 อะตอมต่อบรรทัด
            ที่กด Enter (ไม่นับบรรทัดว่าง) -> รายการยาว ๆ (เช่น VIN 37 คัน)
            ถูก "หั่นข้ามหน้า" ได้ ช่องจำนวน/ราคาแสดงเฉพาะช่วงแรกของรายการ

        กฎ (fill-front): เติมหน้าแรก ๆ ให้เต็ม, ยอดรวม/ลายเซ็นอยู่หน้าสุดท้ายเสมอ
            (<= per_last) โดยหน้าสุดท้ายมีอย่างน้อย 1 แถว
            ตัวอย่าง (นับเป็นแถว): 38 -> [33, 5] , 80 -> [33, 33, 14]

        คืน list ของหน้า แต่ละหน้า = dict:
          {"units": [{"line": record, "desc": [str] | None, "first": bool}, ...],
           "rows": จำนวนแถวจริงของหน้านั้น (template ใช้คำนวณแถวว่างที่ต้องเติม)}
        desc=None -> template ใช้ fallback เดิม (x_custom_name -> name -> product)
        first=False -> ช่วงต่อของรายการที่ถูกหั่น (ไม่แสดงช่องจำนวน/ราคาซ้ำ)
        """
        self.ensure_one()

        # 1) แตกทุกรายการเป็นอะตอม (line, ข้อความบรรทัดนั้น|None, เป็นอะตอมแรกของรายการ)
        atoms = []
        for line in self.invoice_line_ids:
            texts = []
            if line.display_type == "product" and line.x_custom_name_long:
                texts = [s for s in line.x_custom_name_long.splitlines() if s]
            if texts:
                atoms += [(line, t, i == 0) for i, t in enumerate(texts)]
            else:
                atoms.append((line, None, True))

        # 2) ตัดหน้าเป็นช่วงของอะตอม (สูตร fill-front เดิม — ทุกอะตอมสูง 1 แถว)
        total = len(atoms)
        if total <= per_single:
            chunks = [atoms]                        # จบใน 1 หน้า
        else:
            p1 = min(per_first, total - 1)          # หน้าแรก (มีหัวบิล) เติมเต็ม
            chunks = [atoms[:p1]]
            i = p1
            while total - i > per_last:             # เติมหน้ากลางให้เต็ม เหลือให้หน้าสุดท้าย <= per_last
                take = min(per_cont, (total - i) - 1)
                chunks.append(atoms[i:i + take])
                i += take
            chunks.append(atoms[i:])                # หน้าสุดท้าย (แถวที่เหลือ + ยอดรวม/ลายเซ็น)

        # 3) รวมอะตอมติดกันของรายการเดียวกันในหน้าเดียวกันกลับเป็น unit สำหรับ render
        pages = []
        for chunk in chunks:
            units = []
            for line, text, is_first in chunk:
                prev = units[-1] if units else None
                if text is not None and prev and prev["desc"] is not None \
                        and prev["line"].id == line.id:
                    prev["desc"].append(text)
                else:
                    units.append({
                        "line": line,
                        "desc": [text] if text is not None else None,
                        "first": is_first,
                    })
            pages.append({"units": units, "rows": len(chunk)})
        return pages

    def get_cn_totals(self):
        """ยอดรวมท้ายใบลดหนี้ 5 บรรทัด (ตามข้อกำหนดสรรพากร)
        - original = มูลค่าตามใบกำกับภาษีเดิม (ก่อน VAT)
        - diff     = ผลต่าง (มูลค่าที่ลดหนี้ ก่อน VAT)
        - correct  = มูลค่าที่ถูกต้อง = original - diff
        """
        self.ensure_one()
        original = self.reversed_entry_id.amount_untaxed or 0.0
        diff = self.amount_untaxed
        return {
            "original": original,
            "correct": original - diff,
            "diff": diff,
            "vat": self.amount_tax,
            "total": self.amount_total,
        }

    def thai_baht_text(self, amount):
        if not amount:
            return "ศูนย์บาทถ้วน"

        # ฟังก์ชันแปลงตัวเลขเป็นคำอ่านภาษาไทย (Internal Helper)
        def _num2word(n):
            values = ["", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
            places = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]
            exceptions = {"หนึ่งสิบ": "สิบ", "สองสิบ": "ยี่สิบ", "สิบหนึ่ง": "สิบเอ็ด"}

            n_str = str(int(n))
            output = ""
            for i, digit in enumerate(reversed(n_str)):
                if i % 6 == 0 and i > 0:
                    output = places[6] + output

                val = int(digit)
                if val != 0:
                    output = values[val] + places[i % 6] + output

            for k, v in exceptions.items():
                output = output.replace(k, v)
            return output

        # แยกบาทและสตางค์
        amount = float_round(amount, precision_digits=2)
        baht = int(amount)
        satang = int(round((amount - baht) * 100))

        result = ""
        if baht > 0:
            result += _num2word(baht) + "บาท"

        if satang > 0:
            result += _num2word(satang) + "สตางค์"
        else:
            result += "ถ้วน"

        return result


# ---------------------------------------------------------
# ส่วนที่ 4: Wizard ออกใบลดหนี้ (Credit Note)
# ---------------------------------------------------------
class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    def _prepare_default_reversal(self, move):
        # Odoo เดิมเอา reason ไปต่อรวมใน ref เป็น "Reversal of: IVxxx, เหตุผล"
        # เก็บเฉพาะข้อความเหตุผลแยกไว้ที่ x_cn_reason สำหรับพิมพ์ในรายงานใบลดหนี้
        vals = super()._prepare_default_reversal(move)
        if self.reason:
            vals["x_cn_reason"] = self.reason
        return vals
