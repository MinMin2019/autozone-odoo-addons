# autozone_report_fonts/models/font_util.py
import re

from markupsafe import Markup, escape

from odoo import api, models

# ช่วงอักขระ CJK: จีน (รวม Ext-A/compat), คานะญี่ปุ่น, ฮันกึลเกาหลี,
# เครื่องหมายวรรคตอน CJK และอักขระ fullwidth
CJK_RE = re.compile(
    '(['
    '⺀-⿿'  # CJK radicals / Kangxi
    '　-鿿'  # CJK punctuation, kana, bopomofo, Ext-A, CJK unified
    '가-힯'  # Hangul syllables
    '豈-﫿'  # CJK compatibility ideographs
    '︰-﹏'  # CJK compatibility forms
    '＀-￯'  # fullwidth / halfwidth forms
    ']+)'
)

CJK_SPAN = Markup(
    '<span style="font-family:\'Droid Sans Fallback\',sans-serif">%s</span>'
)


class AzFontUtil(models.AbstractModel):
    _name = 'az.font.util'
    _description = 'Autozone Report Font Utilities'

    @api.model
    def wrap_cjk(self, text, nl2br=False):
        """คืน Markup ที่ครอบท่อนอักษร CJK ด้วย span ฟอนต์ Droid Sans Fallback

        wkhtmltopdf (Qt WebKit เก่า) ไม่ทำ per-glyph fallback ข้าม
        font-family ใน stack — glyph ที่ Sarabun ไม่มี (เช่นตัวจีน) จะ
        กลายเป็น □ เฉย ๆ จึงต้องชี้ฟอนต์ให้ท่อน CJK ตรง ๆ แบบนี้:

            <t t-out="line.env['az.font.util'].wrap_cjk(line.name)"/>

        nl2br=True เมื่อใช้แทน t-field ของ Text field (t-field แปลง
        ขึ้นบรรทัดใหม่เป็น <br> ให้อยู่แล้ว ต้องคงพฤติกรรมเดิม)
        """
        if not text:
            return ''
        out = Markup('')
        # re.split ด้วย group: index คี่ = ท่อนที่ regex จับ (CJK)
        for i, chunk in enumerate(CJK_RE.split(text)):
            if not chunk:
                continue
            if i % 2:
                out += CJK_SPAN % chunk
            else:
                out += escape(chunk)
        if nl2br:
            out = Markup('<br/>').join(out.split('\n'))
        return out
