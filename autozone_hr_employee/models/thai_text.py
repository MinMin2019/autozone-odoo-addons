"""Thai date and number wording for the printed employment contract.

Kept here rather than borrowed from custom_invoice_print or
l10n_th_base_utils so the contract does not depend on either module.
"""
_MONTHS = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
           "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
_DIGITS = ["", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
_PLACES = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน"]


def thai_date(value):
    """16 ตุลาคม 2569"""
    if not value:
        return ""
    return f"{value.day} {_MONTHS[value.month]} {value.year + 543}"


def _below_million(n):
    out = []
    digits = str(n)
    size = len(digits)
    for i, ch in enumerate(digits):
        d, place = int(ch), size - i - 1
        if d == 0:
            continue
        if place == 0 and d == 1 and size > 1:
            out.append("เอ็ด")
        elif place == 1 and d == 1:
            out.append("สิบ")
        elif place == 1 and d == 2:
            out.append("ยี่สิบ")
        else:
            out.append(_DIGITS[d] + _PLACES[place])
    return "".join(out)


def thai_number(n):
    """119 -> หนึ่งร้อยสิบเก้า"""
    n = int(n or 0)
    if n == 0:
        return "ศูนย์"
    parts = []
    while n:
        parts.append(n % 1_000_000)
        n //= 1_000_000
    words = ""
    for i, chunk in enumerate(reversed(parts)):
        if chunk:
            words += _below_million(chunk)
        if i < len(parts) - 1:
            words += "ล้าน"
    return words


def baht_text(amount):
    """15000.50 -> หนึ่งหมื่นห้าพันบาทห้าสิบสตางค์ ; 15000 -> หนึ่งหมื่นห้าพันบาทถ้วน"""
    amount = round(float(amount or 0), 2)
    baht, satang = int(amount), int(round((amount - int(amount)) * 100))
    text = thai_number(baht) + "บาท"
    return text + (thai_number(satang) + "สตางค์" if satang else "ถ้วน")
