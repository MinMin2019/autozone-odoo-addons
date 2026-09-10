{
    "name": "Product Image on Document Lines",
    "version": "18.0.1.0.0",
    "category": "Autozone/Tools",
    "author": "Autozone",
    "summary": "แสดงคอลัมน์รูปสินค้าในบรรทัดเอกสาร (ใบโอนย้าย/ใบสั่งขาย)",
    "description": """
เพิ่มคอลัมน์รูปสินค้า (optional) ในตารางบรรทัดของ:
  * stock.picking -> แท็บ Operations (stock.move)
  * sale.order    -> แท็บ Order Lines (sale.order.line)
""",
    "depends": ["stock", "sale"],
    "data": [
        "views/stock_picking_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
}
