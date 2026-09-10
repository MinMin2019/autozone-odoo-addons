{
    "name": "P&L EBDA Line",
    "version": "18.0.1.0.0",
    "category": "Autozone/Accounting",
    "author": "Autozone",
    "summary": "เพิ่มบรรทัด EBDA (กำไรก่อนค่าเสื่อมราคา = Operating Income + Other Income) "
               "ในรายงาน Profit and Loss คั่นก่อน Less Other Expenses",
    "depends": ["account_reports"],
    "data": [
        "data/profit_and_loss_ebda.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
