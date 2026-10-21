"""
PB Health Hospital - one-page advisor pitch card (A4 landscape).

    python pitch_card.py            # -> output/sales_kit/PB_Health_Advisor_Pitch_Card.{pdf,pptx,png}

One content block (CARD) feeds both outputs: an HTML page printed to PDF by
headless Chrome, and an editable PowerPoint built with python-pptx at the same
geometry. Facts come from the PB Health sales team's advisor guide (Oct 2026);
numbers come from the real-call analysis (output/sales_kit/stats.json).

The script deliberately uses the phrases the call tracker listens for
("khud ka hospital", "PB Health Hospital", "MG Road") - see keyword_rules.py.
"""
from __future__ import annotations

import base64
import html
import json
import re
import subprocess
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

import config

OUT = config.OUTPUT_DIR / "sales_kit"
ASSETS = config.BASE_DIR / "assets"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

ORANGE, BLUE, DEEP, INK, GREY, LINE, TINT = "EA4722", "01589F", "004272", "000000", "666666", "D9D9D9", "F3F3F3"
W, H = 11.69, 8.27  # A4 landscape, inches


def stats() -> dict:
    return json.loads((OUT / "stats.json").read_text())


def card(s: dict) -> dict:
    return {
        "eyebrow": "ADVISOR PITCH CARD  ·  HEALTH SALES",
        "title1": "PB Health Hospital",
        "title2": "Pitch it on every call",
        "sub": "Policybazaar's own 100-bed multispeciality hospital  ·  MG Road, Gurugram",
        "script_title": "THE 30-SECOND PITCH  ·  SAY IT WORD FOR WORD",
        # **...** = the words the call tracker listens for
        "script": ("Sir, ek important baat: **Policybazaar ka khud ka hospital** khul gaya hai, "
                   "**PB Health Hospital, MG Road, Gurugram**. India mein yeh akeli insurance company hai "
                   "jiska apna hospital hai. 100-bed multispeciality hospital hai: modular OT, critical care, "
                   "MRI, CT, Cath Lab. Doctors salaried hain, commission nahi, toh sirf zaroori treatment. "
                   "PB customer ko day one se consultation pe 50% off aur tests pe 20% off. Aur claim ki "
                   "tension nahi: policy PB se, claim advisor PB ka, hospital PB ka. 100% claim guarantee."),
        "when_title": "WHEN TO SAY IT",
        "when": [
            "Right after you share the premium: \"ek aur benefit jo sirf PB pe milta hai\"",
            "Customer worries about claim rejection or paperwork",
            "Parents, senior citizens, or BP / sugar / heart in the family",
            "Customer lives in Delhi NCR: open with the location",
        ],
        "outside": "Outside NCR? Lead with the claim promise. The hospital is proof that PB stands behind "
                   "claims. Don't ask them to travel.",
        "points_title": "5 POINTS, IN THIS ORDER",
        "points": [
            ("Own hospital", "India's only insurance company with its own hospital."),
            ("Real hospital", "100-bed multispeciality: modular OT, critical care, MRI, CT, Cath Lab."),
            ("Honest doctors", "Salaried, no commission. Ex-Apollo, Max, Narayana, Manipal, Armed Forces."),
            ("Day-1 savings", "50% off consultations, 20% off tests and scans."),
            ("Claim promise", "100% claim guarantee. A PB RM reaches the hospital within 30 minutes."),
        ],
        "asks_title": "WHEN THE CUSTOMER ASKS",
        "asks_note": f"Real questions from {s['analysed']:,} calls, most asked first",
        "asks": [
            ("\"Kahan hai? Bahut door hai.\"",
             "MG Road, Gurugram. Abhi pehla hospital yahi hai, Noida aur Delhi next. Claim ke time PB ka RM "
             "30 minute mein hospital pahunchta hai."),
            ("\"Hospital hai ya clinic? Admit hota hai?\"",
             "100-bed multispeciality hospital: OT, critical care, MRI, CT, Cath Lab. Consultation se "
             "surgery aur admission tak."),
            ("\"Discount kitna milega?\"",
             "PB customer ko day one se: consultation pe 50% off, tests aur scans pe 20% off."),
            ("\"Doctors kaun hain? Max jaisa hai?\"",
             "Apollo, Max, Narayana, Manipal aur Armed Forces ke senior doctors. Salaried hain, commission nahi."),
            ("\"Zarurat nahi, aage chalo.\"",
             "Bilkul sir. Bas yaad rakhiye: hospital, doctor aur claim advisor, teeno PB ke. Location "
             "WhatsApp kar deta hoon. (Then move on.)"),
        ],
        "do_title": "DO",
        "do": [
            "Say all three: \"Policybazaar ka khud ka hospital\", \"PB Health Hospital\", \"MG Road, Gurugram\" "
            "(the call tracker listens for these).",
            "Say what it treats: \"100-bed multispeciality\".",
            "Pitch on every health call, in or outside NCR.",
        ],
        "dont_title": "DON'T",
        "dont": [
            "Say Noida, Delhi or Faridabad is open: only MG Road is.",
            "Call it a clinic or an \"OPD card\", or give opening dates.",
            "Say only \"apna hospital\": it sounds like \"choose your own\".",
        ],
        "stats": [
            ("4 in 10", "Gurgaon calls mention the hospital today"),
            (f"{s['scope_missing']:.0f}%", "of pitches never say what it treats"),
            (f"{s['ethical']:.0f}%", "mention salaried doctors"),
            ("#1", "customer question: \"Kahan hai?\""),
        ],
        "source": (f"Numbers: {s['team_calls']:,} Gurgaon FF calls (8 Sep - 20 Oct 2026) and {s['analysed']:,} health sales calls "
                   f"({s['period']}), Policybazaar call portal. Facts: PB Health sales team advisor guide, Oct 2026."),
    }


# --------------------------------------------------------------------------- #
# HTML -> PDF
# --------------------------------------------------------------------------- #
def _b64(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _rich(text: str) -> str:
    out = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r'<b class="say">\1</b>', out)


def build_html(c: dict) -> str:
    li = lambda items: "".join(f"<li>{html.escape(x)}</li>" for x in items)
    points = "".join(f'<div class="pt"><span class="num">{i}</span><div><b>{html.escape(t)}</b>'
                     f'<span>{html.escape(d)}</span></div></div>' for i, (t, d) in enumerate(c["points"], 1))
    asks = "".join(f'<div class="ask"><div class="q">{html.escape(q)}</div><div class="a">{html.escape(a)}</div></div>'
                   for q, a in c["asks"])
    stats = "".join(f'<div class="st"><b>{html.escape(v)}</b><span>{html.escape(l)}</span></div>' for v, l in c["stats"])
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;800&family=Nunito:wght@800;900&display=block" rel="stylesheet">
<style>
@page {{ size: A4 landscape; margin: 0 }}
* {{ box-sizing: border-box; margin: 0; padding: 0 }}
body {{ width: 297mm; height: 210mm; font-family: 'DM Sans', Arial, sans-serif; color: #000; background: #fff;
        position: relative; overflow: hidden; font-size: 8.9pt; line-height: 1.3 }}
.wrap {{ position: absolute; inset: 9mm 11mm 9mm 11mm }}
.head {{ display: flex; justify-content: space-between; align-items: flex-start; height: 21mm }}
.eyebrow {{ font-weight: 800; font-size: 8.5pt; letter-spacing: .06em }}
h1 {{ font-family: Nunito, Arial; font-weight: 900; font-size: 21pt; line-height: 1.1; margin-top: 1mm }}
h1 span {{ color: #{ORANGE} }}
.sub {{ font-weight: 500; font-size: 9.5pt; margin-top: 1.2mm }}
.accent {{ width: 46mm; height: 1.6mm; margin-top: 2mm; background: url({_b64(ASSETS / 'accent-gradient.png')}) center/100% 100% }}
.logo {{ height: 13mm }}
.grid {{ display: grid; grid-template-columns: 1.62fr 1fr; gap: 3.5mm; margin-top: 3mm }}
.points {{ margin-top: 3mm }} .prow {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 4mm }}
.card {{ border: 0.75pt solid #{LINE}; border-radius: 3mm; padding: 2.6mm 3.6mm }}
.lab {{ font-weight: 800; font-size: 8.3pt; letter-spacing: .05em; margin-bottom: 1.6mm }}
.lab.o {{ color: #{ORANGE} }} .lab.b {{ color: #{BLUE} }}
.script {{ font-size: 10.2pt; line-height: 1.4; font-weight: 500 }}
.say {{ color: #{ORANGE}; font-weight: 800 }}
ul {{ padding-left: 4mm }} li {{ margin-bottom: .6mm }}
.outside {{ margin-top: 1.5mm; padding: 2mm 2.6mm; background: #{TINT}; border-radius: 2mm; font-size: 8.6pt }}
.pt {{ display: flex; gap: 2.2mm; align-items: flex-start }}
.num {{ font-family: Nunito, Arial; font-weight: 900; color: #{ORANGE}; font-size: 15pt; line-height: 1; min-width: 5mm }}
.pt b {{ display: block; font-size: 9.3pt }} .pt span {{ font-size: 8.7pt }}
.asks {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2mm 4mm }}
.ask .q {{ font-weight: 800; color: #{BLUE}; font-size: 9.1pt }} .ask .a {{ font-size: 8.8pt }}
.note {{ font-weight: 500; color: #{GREY}; font-size: 7.6pt; letter-spacing: 0; margin-left: 2mm }}
.dd {{ display: grid; grid-template-rows: auto auto; gap: 3mm }}
.pill {{ display: inline-block; color: #fff; font-weight: 800; font-size: 8.6pt; padding: .8mm 3.5mm; border-radius: 3mm; margin-bottom: 1.6mm }}
.do .pill {{ background: #{BLUE} }} .dont .pill {{ background: #E64E23 }}
.stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 3mm; margin-top: 3mm; align-items: center }}
.st {{ display: flex; gap: 2mm; align-items: baseline; border-top: 0.75pt solid #{LINE}; padding-top: 1.8mm }}
.st b {{ font-weight: 800; font-size: 15pt; color: #{BLUE}; white-space: nowrap }} .st span {{ font-size: 8.2pt; color: #333 }}
.src {{ position: absolute; left: 11mm; right: 11mm; bottom: 4.6mm; font-size: 7pt; color: #{GREY} }}
.foot {{ position: absolute; left: 0; right: 0; bottom: 0; height: 2.5mm; background: url({_b64(ASSETS / 'footer-gradient.png')}) center/100% 100% }}
</style></head><body><div class="wrap">
<div class="head"><div><div class="eyebrow">{html.escape(c['eyebrow'])}</div>
<h1>{html.escape(c['title1'])} <span>{html.escape(c['title2'])}</span></h1>
<div class="sub">{html.escape(c['sub'])}</div><div class="accent"></div></div>
<img class="logo" src="{_b64(ASSETS / 'pbh-logo.png')}"></div>
<div class="grid">
  <div class="card"><div class="lab o">{html.escape(c['script_title'])}</div><div class="script">{_rich(c['script'])}</div></div>
  <div class="card"><div class="lab b">{html.escape(c['when_title'])}</div><ul>{li(c['when'])}</ul>
    <div class="outside">{html.escape(c['outside'])}</div></div>
</div>
<div class="card points"><div class="lab b">{html.escape(c['points_title'])}</div><div class="prow">{points}</div></div>
<div class="grid">
  <div class="card"><div class="lab o">{html.escape(c['asks_title'])}<span class="note">{html.escape(c['asks_note'])}</span></div>
    <div class="asks">{asks}</div></div>
  <div class="dd"><div class="card do"><span class="pill">{c['do_title']}</span><ul>{li(c['do'])}</ul></div>
  <div class="card dont"><span class="pill">{c['dont_title']}</span><ul>{li(c['dont'])}</ul></div></div>
</div>
<div class="stats">{stats}</div>
</div><div class="src">{html.escape(c['source'])}</div><div class="foot"></div></body></html>"""


def render_pdf(html_path: Path, pdf_path: Path, png_path: Path) -> None:
    common = [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=8000"]
    subprocess.run(common + [f"--print-to-pdf={pdf_path}", html_path.as_uri()], check=True, capture_output=True)
    subprocess.run(common + ["--hide-scrollbars", "--force-device-scale-factor=1.5", "--window-size=1123,794",
                             f"--screenshot={png_path}", html_path.as_uri()], check=True, capture_output=True)


# --------------------------------------------------------------------------- #
# Editable PowerPoint (same layout)
# --------------------------------------------------------------------------- #
MM = 1 / 25.4


def _rgb(hexs: str) -> RGBColor:
    return RGBColor.from_string(hexs)


def _box(slide, x, y, w, h, border=True, fill=None, radius=0.06):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = radius
    if fill:
        shp.fill.solid(); shp.fill.fore_color.rgb = _rgb(fill)
    else:
        shp.fill.background()
    if border:
        shp.line.color.rgb = _rgb(LINE); shp.line.width = Pt(0.75)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _text(slide, x, y, w, h, runs_by_para, anchor=MSO_ANCHOR.TOP, align=PP_ALIGN.LEFT, space_after=2):
    """runs_by_para: list of paragraphs; each paragraph is a list of (text, size, bold, color, font)."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    for i, runs in enumerate(runs_by_para):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        for text, size, bold, color, font in runs:
            r = p.add_run(); r.text = text
            r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = _rgb(color); r.font.name = font
    return tb


def _bullets(items, size, color=INK):
    return [[("•  " + t, size, False, color, "DM Sans")] for t in items]


def build_pptx(c: dict, path: Path) -> None:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    s = prs.slides.add_slide(prs.slide_layouts[6])
    L, R = 11 * MM, W - 11 * MM
    # header
    _text(s, L, 9 * MM, 7.5, 0.2, [[(c["eyebrow"], 8.5, True, INK, "DM Sans")]])
    _text(s, L, 9 * MM + 0.2, 8.4, 0.45, [[(c["title1"] + " ", 21, True, INK, "Nunito Black"),
                                           (c["title2"], 21, True, ORANGE, "Nunito Black")]])
    _text(s, L, 9 * MM + 0.66, 8.4, 0.22, [[(c["sub"], 9.5, False, INK, "DM Sans Medium")]])
    s.shapes.add_picture(str(ASSETS / "accent-gradient.png"), Inches(L), Inches(9 * MM + 0.93), Inches(46 * MM), Inches(1.6 * MM))
    s.shapes.add_picture(str(ASSETS / "pbh-logo.png"), Inches(R - 1.31), Inches(9 * MM), height=Inches(13 * MM))
    # grid geometry (mirrors the HTML)
    top = 9 * MM + 23 * MM + 3.5 * MM
    gap = 4 * MM
    inner = R - L - gap
    lw, rw = inner * 1.62 / 2.62, inner / 2.62
    rx = L + lw + gap
    row1, row2, row3 = 1.62, 0.92, 2.2
    pad = 4 * MM
    # row 1: script | when
    _box(s, L, top, lw, row1)
    _text(s, L + pad, top + 0.12, lw - 2 * pad, 0.2, [[(c["script_title"], 8.3, True, ORANGE, "DM Sans")]])
    runs = []
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", c["script"])):
        runs.append((part, 10.4, i % 2 == 1, ORANGE if i % 2 else INK, "DM Sans Medium"))
    _text(s, L + pad, top + 0.36, lw - 2 * pad, row1 - 0.45, [runs])
    _box(s, rx, top, rw, row1)
    _text(s, rx + pad, top + 0.12, rw - 2 * pad, 0.2, [[(c["when_title"], 8.3, True, BLUE, "DM Sans")]])
    _text(s, rx + pad, top + 0.34, rw - 2 * pad, 0.85, _bullets(c["when"], 9), space_after=1.5)
    _box(s, rx + pad, top + row1 - 0.52, rw - 2 * pad, 0.42, border=False, fill=TINT, radius=0.12)
    _text(s, rx + pad + 0.08, top + row1 - 0.49, rw - 2 * pad - 0.16, 0.38, [[(c["outside"], 8.4, False, INK, "DM Sans")]],
          anchor=MSO_ANCHOR.MIDDLE)
    # row 2: the 5 points as a strip
    y2 = top + row1 + gap
    _box(s, L, y2, R - L, row2)
    _text(s, L + pad, y2 + 0.12, 3, 0.2, [[(c["points_title"], 8.3, True, BLUE, "DM Sans")]])
    tw = (R - L - 2 * pad - 4 * 4 * MM) / 5
    for i, (t, d) in enumerate(c["points"], 1):
        x = L + pad + (i - 1) * (tw + 4 * MM)
        _text(s, x, y2 + 0.36, 0.25, 0.3, [[(str(i), 15, True, ORANGE, "Nunito Black")]])
        _text(s, x + 0.27, y2 + 0.36, tw - 0.27, row2 - 0.42, [[(t, 9.2, True, INK, "DM Sans")],
                                                               [(d, 8.4, False, INK, "DM Sans")]], space_after=0)
    # row 3: asks | do + don't stacked
    y3 = y2 + row2 + gap
    _box(s, L, y3, lw, row3)
    _text(s, L + pad, y3 + 0.12, lw - 2 * pad, 0.2, [[(c["asks_title"] + "   ", 8.3, True, ORANGE, "DM Sans"),
                                                      (c["asks_note"], 7.6, False, GREY, "DM Sans")]])
    colw = (lw - 2 * pad - 4 * MM) / 2
    for i, (q, a) in enumerate(c["asks"]):
        col, row = i % 2, i // 2
        _text(s, L + pad + col * (colw + 4 * MM), y3 + 0.38 + row * 0.62, colw, 0.6,
              [[(q, 9, True, BLUE, "DM Sans")], [(a, 8.6, False, INK, "DM Sans")]], space_after=0.5)
    hh = (row3 - gap) / 2
    for j, (title, items, fill) in enumerate(((c["do_title"], c["do"], BLUE), (c["dont_title"], c["dont"], "E64E23"))):
        y = y3 + j * (hh + gap)
        _box(s, rx, y, rw, hh)
        _box(s, rx + pad, y + 0.1, 0.62, 0.2, border=False, fill=fill, radius=0.5)
        _text(s, rx + pad, y + 0.1, 0.62, 0.2, [[(title, 8.6, True, "FFFFFF", "DM Sans")]], anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER)
        _text(s, rx + pad, y + 0.36, rw - 2 * pad, hh - 0.42, _bullets(items, 8.6), space_after=1)
    y_after = y3 + row3
    # stats strip
    y4 = y_after + gap
    sw = (R - L - 3 * 3 * MM) / 4
    for k, (v, lab) in enumerate(c["stats"]):
        x = L + k * (sw + 3 * MM)
        ln = s.shapes.add_connector(1, Inches(x), Inches(y4), Inches(x + sw), Inches(y4))
        ln.line.color.rgb = _rgb(LINE); ln.line.width = Pt(0.75)
        _text(s, x, y4 + 0.06, sw, 0.36, [[(v + "  ", 15, True, BLUE, "DM Sans"), (lab, 8.2, False, "333333", "DM Sans")]],
              anchor=MSO_ANCHOR.MIDDLE)
    _text(s, L, H - 4.6 * MM - 0.14, R - L, 0.14, [[(c["source"], 7, False, GREY, "DM Sans")]])
    s.shapes.add_picture(str(ASSETS / "footer-gradient.png"), 0, Inches(H - 2.5 * MM), Inches(W), Inches(2.5 * MM))
    prs.save(path)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    c = card(stats())
    html_path = OUT / "PB_Health_Advisor_Pitch_Card.html"
    html_path.write_text(build_html(c), encoding="utf-8")
    render_pdf(html_path, OUT / "PB_Health_Advisor_Pitch_Card.pdf", OUT / "PB_Health_Advisor_Pitch_Card.png")
    build_pptx(c, OUT / "PB_Health_Advisor_Pitch_Card.pptx")
    print("written:", *(p.name for p in sorted(OUT.glob("PB_Health_Advisor_Pitch_Card.*"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
