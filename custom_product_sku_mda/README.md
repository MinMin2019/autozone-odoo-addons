# Autozone Product SKU - Item Approver (`custom_product_sku_mda`)

โมดูลเชื่อม (auto_install) ระหว่าง `custom_product_sku` กับ `custom_master_data_approval`:
กลุ่ม **ผู้อนุมัติ Item Code** imply กลุ่ม **ผู้ดูแลรหัสสินค้า (SKU)** — คนอนุมัติไอเท็มคือคนดูแล SKU
(ออกรหัสใหม่, แก้รหัสหมวด SKU, เมนูประวัติ/ตัวนับ SKU) ไม่ต้องใส่สิทธิ์สองที่

แยกเป็นโมดูลเพราะ prod ยังไม่ติดตั้ง `custom_master_data_approval` — ติดตั้งตัวนั้นเมื่อไร โมดูลนี้ติดตามมาเอง
