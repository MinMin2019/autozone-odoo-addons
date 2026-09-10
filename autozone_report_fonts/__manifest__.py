# autozone_report_fonts/__manifest__.py
{
    'name': 'Autozone Report Fonts (Sarabun)',
    'version': '18.0.1.1.0',
    'summary': 'ฝังฟอนต์ Sarabun + Droid Sans Fallback (CJK) ให้ QWeb PDF report ทุกตัว (ไม่ต้องติดตั้งฟอนต์ที่ OS)',
    'description': """
ฝังฟอนต์ Sarabun มากับโมดูล แล้วประกาศ @font-face ผ่าน asset bundle
'web.report_assets_common' ซึ่งถูกโหลดในทุก report layout ของ Odoo

ผลคือ:
  * ทุก QWeb PDF report ใช้ฟอนต์ Sarabun ได้ทันที
  * ไม่ต้องติดตั้งฟอนต์ที่ระดับ OS ของ server (สำคัญมากเมื่อ Odoo รันเป็น
    Windows Service ด้วย account อื่น เช่น NT Authority\\LocalService
    ซึ่งมองไม่เห็นฟอนต์ที่ติดตั้งแบบ per-user)
  * ย้าย server / ขึ้น Docker ใหม่ ฟอนต์เดินทางไปกับโค้ด

โมดูลอื่นเพียงใส่ 'autozone_report_fonts' ใน depends ก็ใช้ได้เลย
    """,
    'category': 'Autozone/Tools',
    'author': 'Autozone',
    'license': 'LGPL-3',
    'depends': ['web'],
    'assets': {
        'web.report_assets_common': [
            'autozone_report_fonts/static/src/css/report_fonts.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
