"""Put zero-width spaces between Thai words in the contract template.

wkhtmltopdf's WebKit does not know where Thai words end, so it only breaks a
line at a real space. A long clause then overflows and drops to the next line
whole ("ข้อ 6." alone on one line) or splits mid-word ("บริษั|ทฯ"). A
U+200B between words gives it a legal break point and prints as nothing.

Odoo never runs this; it is for whoever edits the contract wording. After
editing report/employment_contract.xml, run (needs `pip install pythainlp`):

    python tools/segment_thai.py report/employment_contract.xml

It is idempotent: existing marks are removed before the text is re-segmented.
Only text between tags inside <template id="report_employment_contract"> is
touched — never attributes, QWeb expressions or record field values.
"""
import re
import sys

from pythainlp.tokenize import word_tokenize

ZWSP = "\u200b"
THAI_RUN = re.compile(r"[\u0E00-\u0E7F]+")


def segment(text):
    text = text.replace(ZWSP, "")
    return THAI_RUN.sub(lambda m: ZWSP.join(word_tokenize(m.group(0), engine="newmm")), text)


def main(path):
    src = open(path, encoding="utf-8").read()
    start = src.index('<template id="report_employment_contract">')
    end = src.index("</template>", start)
    body = re.sub(r">([^<]+)<", lambda m: ">" + segment(m.group(1)) + "<", src[start:end])
    open(path, "w", encoding="utf-8").write(src[:start] + body + src[end:])


if __name__ == "__main__":
    main(sys.argv[1])
