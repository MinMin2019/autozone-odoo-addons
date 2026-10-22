"""Keep employee private addresses in the shape the Thai forms print.

Two problems in the imported data, both fixed on every save and once for the
existing rows by the 18.0.1.2.0 migration:

* private_state_id points at Odoo's English provinces ("Chonburi", code
  TH-20). Production also carries the Thai set ("ชลบุรี", code 20) that every
  customer address already uses; the two match on the number after "TH-".
* private_city is the bare district ("เมือง"). autozone_base_address — the
  formatter every Autozone report uses — expects it to carry its own prefix:
  "อ." outside Bangkok, "เขต" inside it. Typing also left doubled marks
  ("เมืือง" fifteen times, "บ้้านบึง").
"""
import re

_DOUBLED_MARK = re.compile(r"([\u0E31\u0E34-\u0E3A\u0E47-\u0E4E])\1+")
_PREFIX = re.compile(r"^\s*(อำเภอ|อ\.|เขต|เขต\.)\s*")
_THAI = re.compile(r"[฀-๿]")
BANGKOK_CODE = "10"


def thai_state_for(env, state):
    """The Thai-named twin of an English Thai province, or the state itself."""
    if not state or not state.code or not state.code.startswith("TH-"):
        return state
    twin = env["res.country.state"].sudo().search(
        [("country_id", "=", state.country_id.id), ("code", "=", state.code[3:])], limit=1)
    return twin or state


def normalize_city(city, state):
    if not city or not city.strip():
        return city
    text = _DOUBLED_MARK.sub(r"\1", city.strip())
    # อ./เขต only make sense for a Thai address: a Thai province, or no province
    # and a district written in Thai. Anything else only loses the doubled marks.
    is_thai = (state.country_id.code == "TH") if state else bool(_THAI.search(text))
    if not is_thai:
        return text
    bare = _PREFIX.sub("", text).strip()
    if not bare:
        return text
    is_bangkok = bool(state) and state.code in (BANGKOK_CODE, "TH-" + BANGKOK_CODE)
    return ("เขต" if is_bangkok else "อ.") + bare
