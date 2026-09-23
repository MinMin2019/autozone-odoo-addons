# Autozone Custom Addons

โมดูลที่บริษัทเขียนเองทั้งหมด (author = Autozone) — ของ third-party (OCA, Softhealer) อยู่ที่ `D:\odoo18\third_party_addons`

หาในหน้า Apps: filter หมวด **Autozone** ในแถบซ้าย หรือค้น author `Autozone`

## Autozone/Accounting

| โมดูล | คำอธิบาย |
|---|---|
| `asset_module` | เพิ่มรูปภาพ + ฟิลด์ Description/Barcode ในฟอร์ม Asset |
| `custom_analytic_car_reg` | คอลัมน์ Car Registration (ทะเบียนรถ) ในรายการวิเคราะห์ (Analytic Items) ดึงจากใบกำกับ (`x_car_reg_reference`) และใบเสร็จรับเงิน (`license_plate`) ค้นหา/จัดกลุ่มได้ |
| `custom_analytic_code_tags` | ชิป analytic ในฟิลเตอร์รายงานบัญชี (การวิเคราะห์) แสดงเฉพาะตัวย่อสาขา เช่น TMC แทน [TMC] โตโยต้า บ้านบึง |
| `custom_analytic_plan_autofill` | เลือกแผน (โซน) ในฟิลเตอร์การวิเคราะห์ของรายงานบัญชี แล้วเติม analytic account (สาขา) ในแผนนั้นเข้าช่องบัญชีอัตโนมัติ — ได้คอลัมน์รวมโซน + รายสาขาในคลิกเดียว ถอดรายตัวต่อได้ + จัดลำดับคอลัมน์เป็นกลุ่มโซนตามด้วยสาขาของโซนนั้น |
| `custom_asset_prepaid_account` | เปิดให้เลือกบัญชีประเภท Prepayments (ค่าใช้จ่ายจ่ายล่วงหน้า เช่น 152103) ในช่อง Fixed Asset Account / Depreciation Account ของฟอร์มสินทรัพย์ — เดิม Odoo ล็อก domain ไว้แค่ asset_fixed/non_current/current |
| `custom_asset_report_class` | เพิ่มตัวเลือก "จัดกลุ่มตามคลาส" (ฟิลด์ Class → Analytic Account) + คอลัมน์ Analytic Distribution ในรายงาน Depreciation Schedule |
| `custom_asset_report_code` | เพิ่มคอลัมน์ Asset Code (ฟิลด์ Studio) เป็นคอลัมน์แรกในรายงาน Depreciation Schedule |
| `custom_billing_note` | ระบบใบวางบิลลูกค้า (Billing Note) + รายงาน PDF |
| `custom_branch_consumption` | Operation Type "เบิกใช้วัสดุ" (CONS) ทุกคลัง ตัดวัสดุเบิกใช้เข้าบัญชีค่าใช้จ่ายตามหมวดสินค้า + analytic สาขา แทนการเปิด SO ราคา 0 |
| `custom_company_registry_warning` | แจ้งเตือน Company ID ซ้ำเฉพาะเมื่อ Tax ID ซ้ำด้วย (รองรับการเก็บรหัสสาขาใน Company ID) |
| `custom_due_date_display` | แสดง Due Date คู่กับ Payment Terms บนฟอร์มบิล + list view แสดงเป็นวันที่จริงแทน "In X days" |
| `custom_force_vat_rounding` | บังคับปัดเศษ VAT ตามทศนิยมสกุลเงินก่อน post |
| `custom_garage_receipt` | เพิ่มข้อมูลรถยนต์/งานซ่อมในใบเสร็จรับเงิน (VAT และ Non-VAT) |
| `custom_account_hierarchy_fix` | แพตช์ sh_account_parent (Chart of Accounts Hierarchy): แก้ Auto Unfold/ปุ่ม Print ที่พัง, กัน Parent ชี้ตัวเอง-วนลูป-ไม่ใช่ View, แจ้งเตือนเมื่อกางบัญชีที่ไม่มีลูก + กลุ่มสิทธิ์ Account Hierarchy Viewer + ตัวช่วยสร้าง Account Groups จากผังแม่ (ให้ P&L/งบดุล/งบทดลองแสดงเป็นชั้นด้วย Hierarchy and Subtotals) |
| `custom_invoice_print` | พิมพ์ใบกำกับ 5 ใบหัวต่างกัน + ใบลดหนี้ + ฟอร์ม dot-matrix |
| `custom_l10n_th_tax_report_sort` | เรียงรายงานภาษีไทยตาม tax date + คอลัมน์ Doc Ref แสดงเลขเอกสารภายใน (BILL/JV, ใบ cash basis ใช้เลขบิลต้นทาง) |
| `custom_move_analytic_summary` | แท็บสรุปยอดแยกตามสาขา (Analytic) ใน Journal Entry |
| `custom_payment_duplicate` | Action "คัดลอกไปเดือนใหม่" บน list Payment — duplicate หลายใบพร้อมรายการบัญชีที่แก้ไว้ทั้งชุด (งานเงินเดือนรายเดือน) |
| `custom_payment_terms` | ชุด Payment Terms มาตรฐานบริษัท (7 วันหลังรับของ / EOM+20/30/60 / โอนก่อนส่งของ) |
| `custom_petty_cash` | ทะเบียนคุมเงินสดย่อยรายสาขา (ใบเบิก/ใบเคลียร์/ขอเติมเงิน) สร้าง draft vendor bill พร้อม analytic สาขา + ฟอร์มพิมพ์ 3 แบบ |
| `custom_product_classification` | ฟิลด์จัดกลุ่มสินค้า (แบรนด์ · ประเภทย่อย · เจ้าของสินค้า · ชิ้นส่วน · ยี่ห้อรถ · รุ่นรถ · โทนสี · ประเภทงาน · ขั้นตอนงาน + หมวดเดิม) พร้อมเมนูดูแลค่า แถบค้นหาด้านซ้าย ตัวกรอง และจัดกลุ่ม + ต่อเข้ารายงานวิเคราะห์ขาย/ซื้อ/ใบกำกับ ของในคลัง และมูลค่าสต็อก — หมวดสินค้าเหลือหน้าที่กำหนดบัญชีอย่างเดียว |
| `custom_petty_cash_demo` | สร้างเอกสารเงินสดย่อยตัวอย่างครบทุกสถานะตอนติดตั้ง — **สำหรับ DB เทสเท่านั้น ห้ามติดตั้งบน production** |
| `custom_report_ebda` | เพิ่มบรรทัด EBDA (กำไรก่อนค่าเสื่อมราคา = Operating Income + Other Income) ในรายงาน P&L คั่นก่อน Less Other Expenses |
| `custom_report_pl_cost_groups` | P&L: แบ่ง Less Costs of Revenue เป็นกลุ่มย่อยตามช่วงรหัสบัญชี (ค่าแรงงานทางตรง 511 / ค่าสวัสดิการอื่น 512 / ค่าอะไหล่ 52 / ค่าสี 531 / ค่าวัสดุสิ้นเปลืองโรงงาน 532 / ค่าใช้จ่ายผลิตอื่น 54-55) มีหัวกลุ่ม + ยอดรวมย่อย ตามแบบฝ่ายบัญชี; ยอดรวมแม่ยังนับทุกบัญชี Cost of Revenue, บัญชีนอกช่วงไปกลุ่ม "ต้นทุนอื่น" (ซ่อนเมื่อ 0) |
| `custom_report_growth_percent` | คอลัมน์ ±% เปลี่ยนแปลงเทียบงวดก่อนหน้า + % common-size (P&L %ขาย ฐานรายได้หมวด 4, BS %สินทรัพย์ ฐานสินทรัพย์รวม) ต่อท้ายทุกงวดในรายงานการเงิน (BS/P&L/TB ฯลฯ) แทน % เดี่ยวท้ายตารางของ Enterprise + รองรับเปรียบเทียบหลายงวด (จอ/PDF/Excel); TB คิดจากยอดเคลื่อนไหวสุทธิ Debit−Credit |
| `custom_report_xlsx_sum` | Excel จากรายงานบัญชี (BS/P&L/Cash Flow/GL/TB/Journal Audit) แถวยอดรวมเป็นสูตร =SUM() แทนตัวเลขตายตัว + Journal Audit ช่องเงินเป็นตัวเลขจริง (เดิมเป็นข้อความ) |
| `custom_vendor_payment_report` | รายงานการชำระเงินฝั่ง AP เช็คใบวางบิลจาก Vendor (ยอดบิล/WHT/สุทธิ) + รายงาน PDF |
| `custom_tax_invoice_autofill` | บิลซื้อ/ใบลดหนี้ซื้อ: เติมเลขใบกำกับจาก Bill Reference + วันที่ใบกำกับจาก Bill Date ลงแท็บ Tax Invoice อัตโนมัติ (เฉพาะช่องว่าง/ช่องที่ยังไม่แก้มือ, ตามเมื่อแก้ ref, คำนวณ Report Late ให้) |
| `custom_wht_cert_report_fix` | แก้/ปรับฟอร์มใบรับรองหัก ณ ที่จ่าย (ต่อยอด l10n_th_account_wht_cert_form) + WHT Number ใช้เลขใบจ่ายเงิน (PVC/PVB) แทน sequence กลาง ออกเลขตอนกด Done |
| `custom_wht_consolidate` | รวมหลายรายการหัก ณ ที่จ่ายเป็นใบ 50 ทวิใบเดียว |
| `thai_accounting_vouchers` | แยกเมนู RV / PV / JV สำหรับใบสำคัญบัญชีไทย |

## Autozone/Purchase
| `custom_purchase_branch` | ช่อง "สาขา" (analytic) บนหัว PO เติมให้ทุกบรรทัดอัตโนมัติ + บังคับระบุสาขาก่อนยืนยัน PO + คอลัมน์/ตัวกรอง/จัดกลุ่ม "สาขา" บน list PO และบรรทัด PO (multi-edit ได้) + รายงาน Purchase > Reporting > "ซื้อตามสาขา" pivot สินค้า×สาขา + มิติสาขาใน Purchase Analysis |

| โมดูล | คำอธิบาย |
|---|---|
| `custom_po` | ปรับ layout หัวรายงาน PO (ที่อยู่บริษัทกลาง บรรทัดเดียว) |
| `custom_purchase_bill_per_receipt` | ออกบิลผู้ขายแยกตามใบรับสินค้า — รับของ 2 ครั้งกดออกได้ 2 บิล จำนวนตรงกับใบรับใบนั้นเป๊ะ (แปลงหน่วยให้อัตโนมัติ) + ติ๊กพ่วงบรรทัดที่ค้างตั้งหนี้/ไม่ได้อยู่ในใบรับ (เช่น ค่าขนส่ง) + คอลัมน์-ฟิลเตอร์ "สถานะตั้งหนี้" บนรายการใบรับ + เมนู Accounting › Vendors › "ใบรับสินค้าค้างตั้งหนี้" ให้ทีมบัญชีกดออกบิลจากแถวได้เองโดยไม่ต้องเข้าเมนูจัดซื้อ/คลัง |
| `custom_purchase_bill_autocomplete` | ช่อง Auto-Complete บนบิลผู้ขาย: กรองบรรทัดที่ไม่มีอะไรให้ตั้งหนี้ (qty 0) ออกเหมือนปุ่ม Create Bill + เตือนเมื่อเลือก PO ที่ยังไม่มีของรับ + ให้กลุ่มบัญชี Billing เห็นช่องนี้โดยไม่ต้องมีสิทธิ์จัดซื้อ |
| `custom_purchase_date_lock` | ล็อควัน "คาดว่าจะมาถึง" — บรรทัดสินค้าใหม่สืบทอดวันจากหัว PO แทนการคำนวณจาก lead time |
| `custom_purchase_pending_receipt` | นับบรรทัด PO ค้างรับบน list view จัดซื้อ |
| `custom_purchase_recreate_receipt` | ปุ่ม "สร้างใบรับใหม่" บน PO เมื่อใบรับสินค้าถูกยกเลิกไปหมดแล้วแต่ยังมีของค้างรับ (Odoo นับใบรับที่ยกเลิก = รับครบ ปุ่ม Receive Products จึงหายไป) |
| `custom_purchase_vendor_only` | ช่อง Vendor ในใบสั่งซื้อแสดงเฉพาะผู้ขาย + checkbox "Is a Vendor" กำหนดเองบนฟอร์ม Contact (แท็บ Sales & Purchase) |

## Autozone/Inventory

| โมดูล | คำอธิบาย |
|---|---|
| `custom_stock_card` | บัญชีคุมสินค้า (Stock Card) เมนู Inventory › Reporting: ยกมา/รับ/จ่าย/ยกไป ต่อสินค้าต่อสาขา (ติ๊ก "แยกตำแหน่งในสาขา" ได้) ทั้งจำนวนและมูลค่า + รายละเอียดการเคลื่อนไหวแบบ running balance + PDF แนวนอน + Excel (สรุป/สรุปสาขา/รายละเอียด) — v1.1 รับ/จ่ายแตก 9 ประเภท (รับซื้อ/รับคืนลูกค้า/โอนเข้า/ปรับเพิ่ม-รับอื่น | ขาย/ส่งคืนผู้ขาย/โอนออก/เบิกใช้/ปรับลด-จ่ายอื่น; ส่งขายราคา 0 = เบิกใช้, ผ่านคลังพัก = โอน) + ตัวกรองประเภทรายการ + มูลค่ารวมต่อสาขาแยกประเภท (ตรวจโอนออก = โอนเข้า) — มูลค่าใช้ต้นทุนจาก valuation layer ของ move ถ้าไม่มี (โอนระหว่างสาขา) ใช้ต้นทุนปัจจุบันของสินค้า |
| `custom_stock_aging` | อายุสินค้าคงคลัง (Stock Aging) เมนู Inventory › Reporting: ของคงเหลือ ณ วันที่ ต่อสินค้าต่อสาขา แบ่งช่วง 0-30/31-60/61-90/91-180/181-365/เกิน 365 วัน (จำนวน+มูลค่า) ไล่ย้อนว่ามาจากการรับเข้าครั้งไหน (FIFO ต่อสาขา อายุนับใหม่เมื่อโอนเข้า) + รับ/จ่ายล่าสุด + วันไม่เคลื่อนไหว (ใช้หา slow-moving) + list/pivot/graph + PDF + Excel |
| `custom_stock_count_variance` | ผลต่างตรวจนับ (Count Variance) เมนู Inventory › Reporting: โหมด "รอปรับปรุง" (นับแล้วยังไม่ Apply ให้ตรวจมูลค่าผลต่างก่อนอนุมัติ + รายการถึงกำหนดนับแต่ยังไม่นับ) และ "ปรับปรุงแล้ว" (ประวัติตามช่วงวันที่ ระบบก่อนปรับ/ยอดนับ/ผลต่าง/ผู้กด Apply) สรุปต่อสาขา ขาด/เกิน/สุทธิ/ความแม่นยำ % + list/pivot/graph + PDF มีช่องลายเซ็น + Excel |
| `custom_stock_gl_recon` | กระทบยอดสต็อกกับบัญชี (Stock vs GL) เมนู Inventory › Reporting และ Accounting › Reporting: เทียบ ณ วันที่ ของในคลัง (จำนวน×ต้นทุน) / ระบบสต็อก (valuation layer) / ยอดในบัญชี 141xxx (GL) แยกสาเหตุผลต่างอัตโนมัติ (SVL ไม่มี JE, JE ไม่มี SVL, cut-off, สินค้าผี) เจาะรายสินค้า/รายสมุด + บัญชีพักขาเข้า-ขาออก คงค้าง/ยังไม่จับคู่ + PDF + Excel |
| `custom_stock_negative` | สต็อกติดลบ (Negative Stock) เมนู Inventory › Reporting: โหมด "ติดลบ ณ วันที่" (จำนวน/มูลค่า/ติดลบตั้งแต่/กี่วัน/เอกสารที่ทำให้ติดลบ/ผู้ทำ/ของค้างรับที่กำลังเข้ามา + พอแก้ไหม + คำแนะนำ) และ "ประวัติรายการที่ทำให้ติดลบ" ตามช่วงวันที่ (ดูว่ากระบวนการไหนสร้างปัญหาบ่อย) + list/pivot/graph + PDF + Excel |
| `custom_stock_slow_moving` | สินค้าเคลื่อนไหวช้า / ไม่เคลื่อนไหว (Slow / Dead Stock) เมนู Inventory › Reporting: คงเหลือ+มูลค่า ต่อสินค้าต่อสาขา (หรือรวมทุกสาขา), การใช้ย้อนหลัง 30/90/180/365 วัน, ใช้ล่าสุด, เฉลี่ย/เดือน, พอใช้กี่เดือน, จัดชั้น Dead/Slow/Normal ตามเกณฑ์ที่ตั้งเอง + "สาขาที่ยังใช้ใน 90 วัน" สำหรับโยกของแทนซื้อใหม่ + list/pivot/graph + PDF + Excel |
| `custom_stock_turnover` | อัตราหมุนเวียนสินค้า (Inventory Turnover) เมนู Inventory › Reporting: ช่วงวันที่ → ยกมา/รับ/ใช้ไป/จ่ายอื่น/ยกไป, มูลค่าเฉลี่ยที่ถือ ((ยกมา+ยกไป)/2 หรือเฉลี่ยสิ้นเดือน), Turnover รอบ/ปี, Days of Inventory คำนวณ 4 ระดับในครั้งเดียว (ทั้งบริษัท/สาขา/หมวด/สินค้า×สาขา) + list/pivot/graph + PDF + Excel 4 ชีท |
| `custom_stock_matrix` | Stock Matrix สินค้า × สาขา (เมนู Inventory › Reporting): ยอดคงเหลือ ณ วันที่ ทุกสาขาเรียงเป็นคอลัมน์ในหน้าเดียว (pivot แถว=สินค้า คอลัมน์=สาขา สลับจำนวน/มูลค่า) + ฟิลเตอร์ "มีของมากกว่า 1 สาขา หรือมีสาขาติดลบ" หาโอกาสโยกของ + Excel ตารางจริง 2 ชีท + PDF แนวนอนแบ่งสาขาชุดละ 13 |
| `custom_stock_consumption_summary` | สรุปเบิกใช้วัสดุตามสาขา (เมนู Inventory › Reporting และ Accounting › Reporting): ช่วงวันที่ → มูลค่าเบิกใช้สุทธิ (หักเบิกคืน) ต่อสาขา × บัญชีค่าใช้จ่าย / หมวดสินค้า / เดือน / สินค้า จากใบเบิกใช้ CONS + ตัวเลือกรวม "ส่งขายราคา 0" วิธีเดิม + pivot/list/graph + PDF + Excel 4 ชีท |
| `custom_stock_abc` | ABC Analysis (เมนู Inventory › Reporting): จัดชั้นสินค้า A/B/C แบบ Pareto จากมูลค่าที่ใช้ไป / จำนวนที่ใช้ / มูลค่าคงเหลือ ในช่วงวันที่ (เกณฑ์ 80/95 ตั้งได้) ทั้งบริษัทหรือแยกรายสาขา + ตาราง Pareto + ปุ่ม "บันทึกชั้นลงสินค้า" (ฟิลด์ ชั้น ABC + วันที่ บนแท็บ Inventory ของสินค้า, ฟิลเตอร์ ABC ในรายการสินค้า) + list/pivot/graph + PDF + Excel |
| `custom_stock_backdate` | ช่อง "Actual Date (Backdate)" บนใบโอน/ใบรับ — กรอกก่อน Validate แล้ววันนั้นจะประทับลง Effective Date, stock move/move line, valuation layer และ JE อัตโนมัติ (ใช้กรณีคีย์รับของย้อนหลัง) + ปุ่ม "แก้วันที่รับจริง" สำหรับใบที่ Validate ไปแล้วด้วยวันผิด + Action ทำเป็นชุดจากหน้า list ยึดวันที่ตามกำหนดการ (ผู้จัดการบัญชีเท่านั้น) |
| `custom_branch_transfer` | ใบโอนสินค้าไปสาขา (BTyyyymmNNNNN) ครอบ Flow B: ส่วนกลางเลือกสาขา+สินค้าหลายบรรทัด กดยืนยัน → ระบบสร้าง TOUT+TIN คู่กันจาก route "Supply Product from H.O." เอง, ปุ่ม "ส่งของ"/"รับของทั้งหมด"/"รับบางส่วน" บนใบเดียว, สถานะ ร่าง→รอส่ง→ส่งแล้ว→รับบางส่วน→รับครบ, PDF ใบโอน + กันพลาด: ห้ามสร้าง TOUT/TIN มือ, ห้าม Validate TIN ก่อน TOUT Done — เมนู Inventory > Operations > โอนสินค้าไปสาขา / รับโอนจากส่วนกลาง |
| `custom_picking_xlsx` | ปุ่ม "Export Excel" บนฟอร์มใบรับของ/ใบโอน/ใบเบิกใช้ทุกประเภท — ส่งออกหัวใบ + รายการสินค้า (รหัส ชื่อ หมวด Demand Quantity หน่วย Lot) เป็น .xlsx; คอลัมน์ต้นทุน/มูลค่าเห็นเฉพาะ Inventory Manager หรือผู้มีสิทธิ์อ่านบัญชี |

## Autozone/Sales

| โมดูล | คำอธิบาย |
|---|---|
| `crm_blanket_order_kpi` | Opportunity เป็น control tower ของ blanket-order contract (KPI) |
| `custom_exact_subtotal` | ช่อง "ยอดรวมกำหนดเอง" บนบรรทัดใบเสนอราคา/ใบแจ้งหนี้ — กรอกยอดให้ตรง PO ลูกค้าที่ใช้ราคาต่อหน่วยทศนิยม 4 ตำแหน่ง (เช่น 168 x 733.2236 = 123,181.56) โดยไม่ต้องเพิ่ม Decimal Accuracy ทั้งระบบ + ใบกำกับ/ใบลดหนี้ A4 แสดงราคา 4 ตำแหน่งเฉพาะใบที่ใช้ (ฟอร์ม dot-matrix ไม่แตะ) |
| `custom_crm_tracking` | เพิ่ม chatter tracking บน crm.lead: วันคาดว่าจะปิด / Priority / Probability / โปรเจกต์ (analytic) |
| `sale_service_remaining_qty` | ติดตามจำนวนคงเหลือของสินค้า service ในใบสั่งขาย |

## Autozone/Access

| โมดูล | คำอธิบาย |
|---|---|
| `custom_access_role_builder` | สร้าง role การเข้าถึงแบบคลิกเลือก (role/menu whitelist) |
| `custom_warehouse_scope` | จำกัดข้อมูลสต็อกรายผู้ใช้ตามคลังที่อนุญาต (record rule) |

## Autozone/Master Data

| โมดูล | คำอธิบาย |
|---|---|
| `custom_master_data_approval` | workflow อนุมัติข้อมูลหลัก (Vendor/Customer = หัวหน้าบัญชี, Item Code = ผู้จัดการบัญชี): หน้างานสร้าง+ส่งอนุมัติแล้วล็อคแก้ไข, บล็อกยืนยันทุกทรานแซคชัน (SO/PO/บิล/จ่ายเงิน/ใบโอน/50ทวิ) ของข้อมูลที่ยังไม่อนุมัติ, ผูกสิทธิ์กับ role builder อัตโนมัติ — เมนู "อนุมัติข้อมูลหลัก" |

## Autozone/HR

| โมดูล | คำอธิบาย |
|---|---|
| `custom_hr_loan` | ทะเบียนเงินกู้สวัสดิการพนักงาน (เลขที่ LCปี พ.ศ./NNN แก้ได้, เงินต้น/ตารางงวด/ยอดคงเหลือ) + ปุ่ม "หักเงินกู้พนักงาน" บน Payslip Batch ดันงวดที่ถึงกำหนดเป็น Other Input รหัส LOAN — เมนูอยู่ใต้ Accounting > เงินกู้พนักงาน |
| `import_payslip_inputs` | นำเข้า Other Inputs (เบี้ยเลี้ยง/หักเงิน) จาก Excel เข้า Payslip Batch |
| `custom_hr_attendance_sync` | ดึงเวลาตอกบัตรจากเครื่องสแกนนิ้ว (ฐาน BpControl บน SQL Server) เข้า Attendances อัตโนมัติทุกวัน — 1 วัน = สูงสุด 3 ช่วง (เช้า/บ่าย/เย็น), จับคู่ด้วย Registration Number, แปลงเวลาไทย→UTC, ดึงซ้ำไม่เกิดข้อมูลซ้ำ + เมนู "ดึงเวลาจากเครื่องสแกน" และ "ประวัติการดึงเวลา" ใต้ Attendances > Configuration |

## Autozone/Tools

| โมดูล | คำอธิบาย |
|---|---|
| `autozone_base_address` | method กลางจัดรูปแบบข้อมูลคู่ค้าไทยบน res.partner: ที่อยู่ (`get_thai_address` / `get_thai_address_lines` / `get_thai_state_display`) + ป้ายสาขา (`get_thai_branch_display` = สำนักงานใหญ่/สาขาที่ X, `get_thai_vat_line` = เลขผู้เสียภาษี+สาขา) — รายงานใหม่ทุกตัวต้องเรียกใช้ตัวนี้ ห้ามต่อ string เอง |
| `autozone_report_fonts` | ฝังฟอนต์ Sarabun ให้ PDF report ทุกตัว (ไม่ต้องลงฟอนต์ที่ OS) |
| `custom_chatter_toggle` | ปุ่มซ่อน/แสดง chatter บนฟอร์มใบสั่งขาย |
| `custom_delete_log` | Autozone Audit Log: log การลบ+archive record (ใคร/เมื่อไหร่/snapshot), log การล็อกอินสำเร็จ-ล้มเหลวพร้อม IP, log ติดตั้ง/อัปเกรดโมดูล, และ chatter-track field อ่อนไหว (บัญชีธนาคาร vendor, ราคาขาย/ต้นทุน, เงื่อนไขชำระเงิน, วงเงินเครดิต) — ดูที่ Settings > Technical > Audit Log |
| `custom_line_product_image` | คอลัมน์รูปสินค้าในบรรทัดเอกสาร (โอนย้าย/ใบสั่งขาย) |
| `custom_studio_fields` | สำรองฟิลด์ Studio (Asset Code/Location บน asset, Invoicing Journal บน SO) เป็นโค้ด — **ยังไม่ติดตั้ง** เก็บไว้ใช้ตอนอัพเกรด/ย้ายฐาน ดู README ในโมดูล |

## กติกา

- โมดูลใหม่ที่เขียนเอง: วางโฟลเดอร์ที่นี่, ตั้ง `category` เป็น `Autozone/<หมวด>`, `author` = `Autozone` แล้วเพิ่มแถวใน README นี้
- **ห้ามเปลี่ยนชื่อโฟลเดอร์โมดูลที่ติดตั้งแล้ว** (ชื่อโฟลเดอร์ = identity ของโมดูลใน DB)
- ของ third-party ห้ามแก้ manifest — วางไว้ที่ `third_party_addons` เพื่อให้อัปเดตจากต้นทางได้
