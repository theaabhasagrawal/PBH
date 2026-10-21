"""
Generates the 2-page PB Health Hospital telesales reference deck / battlecard.

    python deck_generator.py                  # -> output/PB_Health_Sales_Deck.html + .pdf
    python deck_generator.py --with-baseline  # adds a "where we are today" strip from pb_health.db

Page 1 - Master Pitch Script : the 30-second pitch (same script as pitch_card.py), the
          5 pillars, where the hospital is (MG Road, Gurugram only), customer
          savings, close.
Page 2 - Objection Battlecards: word-for-word answers to the real customer
          questions, approved facts and do / don't quick reference.

All copy lives in the DECK dict below so ops/training can edit it without
touching layout code. Facts were approved by PB Health strategy (Oct 2026) and
must match pitch_card.py and advisor_playbook.js - change all three together.
"""
from __future__ import annotations

import argparse
import html
from datetime import date

import config

# --------------------------------------------------------------------------- #
# CONTENT (edit here)
# --------------------------------------------------------------------------- #
DECK = {
    "title": "PB Health Hospital",
    "subtitle": "Telesales Pitch Card - MG Road, Gurugram",
    "hook": {
        # same script as pitch_card.py - keep the two in step
        "hinglish": ("Sir, ek important baat: <b>Policybazaar ka khud ka hospital</b> khul gaya hai, "
                     "<b>PB Health Hospital, MG Road, Gurugram</b>. India mein yeh akeli insurance company hai jiska apna "
                     "hospital hai. <b>100-bed multispeciality</b> hospital hai: modular OT, critical care, MRI, CT, Cath Lab. "
                     "Doctors <b>salaried</b> hain, commission nahi, toh sirf zaroori treatment. PB customer ko day one se "
                     "<b>consultation pe 50% off</b> aur <b>tests pe 20% off</b>. Aur claim ki tension nahi: policy PB se, "
                     "claim advisor PB ka, hospital PB ka. <b>100% claim guarantee</b>."),
        "english": ("Policybazaar has opened its own hospital, PB Health Hospital, on MG Road, Gurugram - India's only insurance "
                    "company with its own hospital. 100-bed multispeciality: modular OT, critical care, MRI, CT, Cath Lab. "
                    "Salaried doctors, no commission. 50% off consultations and 20% off tests from day one. Policy, claim "
                    "advisor and hospital are all PB: 100% claim guarantee."),
        "when": ["Right after you share the premium: \"ek aur benefit jo sirf PB pe milta hai\"",
                 "Customer worries about claim rejection or paperwork",
                 "Parents, senior citizens, or BP / sugar / heart in the family",
                 "Customer lives in Delhi NCR: open with the location",
                 "Every other health call too - 96% of customers never ask"],
    },
    "pillars": [
        ("Policybazaar's own hospital",
         "India's only insurance company with its own hospital. First flagship: MG Road, Gurugram.",
         "\"Policybazaar ka khud ka hospital - PB Health Hospital, MG Road, Gurugram.\""),
        ("Real multispeciality hospital",
         "100 beds. Modular OT, MRI, CT scan, Cath Lab, digital X-ray, critical care, in-house lab.",
         "\"Consultation se surgery aur admission tak, sab ek jagah.\""),
        ("Honest, senior doctors",
         "Salaried, no commission. Specialists from Apollo, Max, Narayana, Manipal and the Armed Forces.",
         "\"Doctor ko faltu test likhne ka koi fayda nahi - toh sirf zaroori treatment.\""),
        ("Day-1 savings",
         "50% off specialist consultations, 20% off tests and scans, from day one.",
         "\"PB customer ko day one se consultation pe 50% off, tests pe 20% off.\""),
        ("The claim promise",
         "100% claim guarantee. A PB advisor / RM reaches the hospital within 30 minutes for paperwork.",
         "\"Policy PB se, claim advisor PB ka, hospital PB ka.\""),
    ],
    "where": [
        "Only PB Health Hospital, MG Road, Gurugram is open today.",
        "Next: Noida and Delhi, then Mumbai and Bengaluru. Never give dates.",
        "Customer in Delhi NCR: open with the location.",
        "Customer outside NCR: lead with the claim promise; the hospital is proof PB stands behind claims. Don't ask them to travel.",
    ],
    "family_perks": [
        "50% off specialist consultations",
        "20% off tests and scans",
        "From day one of the policy",
        "100% claim guarantee",
        "PB RM at the hospital within 30 minutes for paperwork",
    ],
    "close": ("\"Main abhi PB Health Hospital, MG Road ki location WhatsApp kar deta hoon - jab bhi zarurat ho, "
              "wahan PB customer ke benefits milenge.\""),
    # Objection battlecards: (title, customer says, you say, proof point) - real questions, most asked first
    "objections": [
        ("Kahan hai? Bahut door hai.",
         "\"Kahan pe hai yeh hospital?\" (110 calls - by far the most asked)",
         "\"MG Road, Gurugram. Abhi pehla hospital yahi hai; Noida aur Delhi next. Claim ke time PB ka RM 30 minute mein "
         "hospital pahunchta hai.\"",
         "Only MG Road is open - never say Noida, Delhi or Faridabad is."),
        ("Hospital hai ya clinic?",
         "\"That's a hospital also ya phir koi walk-in facility?\"",
         "\"100-bed multispeciality hospital: modular OT, critical care, MRI, CT, Cath Lab. Consultation se surgery aur "
         "admission tak.\"",
         "Say 'OT, critical care' explicitly - never 'clinic' or 'OPD card'."),
        ("Discount kitna milega?",
         "\"Matlab discount kitna mil jayega?\"",
         "\"PB customer ko day one se: consultation pe 50% off, tests aur scans pe 20% off.\"",
         "Only 50% / 20%. Not 25%, 30%, 75% or 'free'."),
        ("Doctors kaun hain?",
         "\"Yahan ke MD kaun hai? Max jaisa hai?\"",
         "\"Apollo, Max, Narayana, Manipal aur Armed Forces ke senior doctors. Salaried hain, commission nahi.\"",
         "Same senior expertise + no billing incentive."),
        ("Meri policy chalegi?",
         "\"Meri policy wahan cashless chalegi?\"",
         "\"Apni policy ka naam bataiye, main abhi check karke batata hoon ki wahan cashless milega ya nahi.\"",
         "Never guess - confirm the insurer live."),
        ("Zarurat nahi, aage chalo",
         "\"Mujhe nahi chahiye, hospital mein mujhe nahi jaana.\"",
         "\"Bilkul sir. Bas yaad rakhiye: hospital, doctor aur claim advisor, teeno PB ke. Location WhatsApp kar deta hoon.\"",
         "Say it once, then move on."),
        ("Insurance company ka hospital - wahin bhejoge?",
         "\"Aap apne hi hospital mein bhejna chahte ho na?\"",
         "\"Bilkul nahi sir - hospital ki choice hamesha aapki hai. PB Health Hospital ek extra option hai jahan doctors "
         "salaried hain aur PB customer ko 50% / 20% off milta hai.\"",
         "Position as a choice, never a restriction."),
    ],
    "dos": [
        "Say: \"Policybazaar ka khud ka hospital\", \"PB Health Hospital\", \"MG Road, Gurugram\"",
        "Say what it treats: \"100-bed multispeciality\"",
        "Give the reason to trust: salaried doctors",
        "Pitch on every health call, in or outside NCR",
    ],
    "donts": [
        "Say Noida, Delhi or Faridabad is open - only MG Road is",
        "Give opening dates for new hospitals",
        "Call it a clinic or an \"OPD card\"",
        "Quote any discount other than 50% / 20%",
    ],
    "scorecard_note": ("How pitches are tracked: a call counts as pitched when you say the hospital phrases - \"khud ka "
                       "hospital\", \"PB Health Hospital\", \"MG Road\". Generic words like discount or claims don't count "
                       "(see output/sales_kit/PB_Health_Pitch_Keywords.xlsx)."),
}

# Approved facts (page 2) - same as the advisor playbook appendix
FACTS = [
    ("Location", "MG Road, Gurugram - the only PB Health hospital open today"),
    ("Size and type", "100-bed multispeciality flagship hospital"),
    ("Facilities", "Modular OT, MRI, CT scan, Cath Lab, digital X-ray, critical care, in-house lab"),
    ("Doctors", "Salaried (non-commission); specialists from Apollo, Max, Narayana, Manipal; Armed Forces doctors"),
    ("Savings", "50% off consultations, 20% off tests and scans, from day one"),
    ("Claims", "100% claim guarantee; PB RM at the hospital within 30 minutes"),
    ("Positioning", "India's only insurance company with its own hospital"),
    ("Expansion", "Noida and Delhi next, then Mumbai and Bengaluru - no dates"),
]

BRAND = {"navy": "#0B2A4A", "teal": "#00A3A1", "orange": "#F26B21", "light": "#EEF6F8", "ink": "#1E2A35",
         "muted": "#5B6B79", "red": "#C0392B", "green": "#1E8E5A"}


# --------------------------------------------------------------------------- #
# Baseline strip (optional)
# --------------------------------------------------------------------------- #
def baseline_strip() -> str | None:
    """'Where we are today' line from the real-call analysis (output/sales_kit/stats.json)."""
    try:
        import json
        st = json.loads((config.OUTPUT_DIR / "sales_kit" / "stats.json").read_text())
        return (f"Where we are today ({st['period']}): {st['team_actual']:.0f}% of Gurgaon calls mention the hospital | "
                f"{st['scope_missing']:.0f}% of pitches never say what it treats | {st['ethical']:.0f}% mention salaried "
                f"doctors | MG Road named in {st['mg_road']:.0f}% of pitches")
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# HTML renderer
# --------------------------------------------------------------------------- #
def _where_cards() -> str:
    return "\n".join(f"""<div class="hub"><div class="hub-n">{i}</div><div>{html.escape(w)}</div></div>"""
                     for i, w in enumerate(DECK["where"], 1))


def render_html(strip: str | None = None) -> str:
    d, c = DECK, BRAND
    hook = d["hook"]
    pillars = "\n".join(
        f"""<div class="pillar"><div class="pn">{i}</div><div><div class="pt">{html.escape(t)}</div>
        <div class="pd">{html.escape(desc)}</div><div class="say">{html.escape(say)}</div></div></div>"""
        for i, (t, desc, say) in enumerate(d["pillars"], 1))
    perks = "".join(f"<li>{html.escape(p)}</li>" for p in d["family_perks"])
    when = "".join(f"<li>{html.escape(w)}</li>" for w in hook["when"])
    objections = "\n".join(
        f"""<div class="obj"><div class="oh"><span class="on">{i}</span>{html.escape(t)}</div>
        <div class="cs"><b>Customer:</b> {html.escape(cs)}</div>
        <div class="ys"><b>You:</b> {html.escape(ys)}</div>
        <div class="tip">&#9658; {html.escape(tip)}</div></div>"""
        for i, (t, cs, ys, tip) in enumerate(d["objections"], 1))
    finder = "".join(f"<tr><td><b>{html.escape(a)}</b></td><td>{html.escape(b)}</td></tr>" for a, b in FACTS)
    dos = "".join(f"<li>{html.escape(x)}</li>" for x in d["dos"])
    donts = "".join(f"<li>{html.escape(x)}</li>" for x in d["donts"])
    strip_html = f'<div class="strip">{html.escape(strip)}</div>' if strip else ""
    today = date.today().strftime("%d %b %Y")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PB Health Pitch Card</title>
<style>
:root {{ --navy:{c['navy']}; --teal:{c['teal']}; --orange:{c['orange']}; --light:{c['light']}; --ink:{c['ink']}; --muted:{c['muted']}; --red:{c['red']}; --green:{c['green']}; }}
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:#d9dee3; font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; color:var(--ink); font-size:9.6pt; line-height:1.32; }}
.page {{ width:210mm; height:297mm; margin:10mm auto; background:#fff; padding:9mm 10mm; position:relative; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,.15); }}
@media print {{ body {{ background:#fff; }} .page {{ margin:0; box-shadow:none; page-break-after:always; }} .page:last-child {{ page-break-after:auto; }} }}
@media screen and (max-width: 820px) {{ .page {{ width:auto; height:auto; margin:8px; }} .cols, .cols3 {{ grid-template-columns:1fr !important; }} }}
header {{ display:flex; justify-content:space-between; align-items:flex-end; background:var(--navy); color:#fff; margin:-9mm -10mm 4mm; padding:6mm 10mm 4mm; border-bottom:4px solid var(--orange); }}
header h1 {{ margin:0; font-size:20pt; letter-spacing:.3px; }} header h1 span {{ color:var(--teal); }}
header .sub {{ font-size:10pt; opacity:.9; }} header .tag {{ text-align:right; font-size:8pt; opacity:.85; }}
h2 {{ font-size:11pt; color:var(--navy); margin:3mm 0 1.5mm; text-transform:uppercase; letter-spacing:.6px; border-left:4px solid var(--teal); padding-left:2mm; }}
.hook {{ background:linear-gradient(135deg,#FFF4EC,#FFE7D6); border:1.5px solid var(--orange); border-radius:6px; padding:3mm 4mm; }}
.hook .lbl {{ font-weight:700; color:var(--orange); font-size:8.5pt; text-transform:uppercase; }}
.hook p {{ margin:1mm 0; font-size:10.4pt; }} .hook .en {{ color:var(--muted); font-size:8.6pt; font-style:italic; }}
.cols {{ display:grid; grid-template-columns: 1.25fr 1fr; gap:4mm; }}
.cols3 {{ display:grid; grid-template-columns: 1fr 1fr; gap:3mm; }}
.pillar {{ display:flex; gap:2.5mm; padding:1.6mm 0; border-bottom:1px dashed #cfd8df; }}
.pn, .hub-n, .on {{ flex:none; width:6mm; height:6mm; border-radius:50%; background:var(--teal); color:#fff; font-weight:700; display:flex; align-items:center; justify-content:center; font-size:8.5pt; }}
.pt {{ font-weight:700; color:var(--navy); }} .pd {{ font-size:8.6pt; }} .say {{ font-size:8.6pt; color:var(--orange); font-style:italic; }}
.hub {{ display:flex; gap:2.5mm; align-items:flex-start; background:var(--light); border-radius:5px; padding:1.6mm 2mm; margin-bottom:1.4mm; }}
.hub-n {{ background:var(--navy); }}
.small {{ font-size:8pt; color:var(--muted); }}
.box {{ background:var(--light); border-radius:6px; padding:2mm 3mm; }}
.box ul {{ margin:1mm 0 0; padding-left:4.5mm; }} .box li {{ margin:.5mm 0; }}
.perks {{ background:#EAF7EF; border:1.5px solid var(--green); }}
.close {{ background:var(--navy); color:#fff; border-radius:6px; padding:2.5mm 4mm; margin-top:3mm; font-size:9.6pt; }}
.close b {{ color:var(--teal); }}
.score {{ font-size:7.8pt; color:var(--muted); border-top:1px solid #dfe5ea; margin-top:2.5mm; padding-top:1.5mm; }}
.strip {{ background:#FFF8E1; border:1px solid #F5C451; border-radius:4px; padding:1.5mm 3mm; font-size:8pt; margin-bottom:2mm; }}
.objgrid {{ display:grid; grid-template-columns:1fr 1fr; gap:2.4mm; }}
.obj {{ border:1px solid #cfd8df; border-top:3px solid var(--orange); border-radius:5px; padding:1.8mm 2.5mm; font-size:8.5pt; break-inside:avoid; }}
.oh {{ font-weight:700; color:var(--navy); font-size:9.4pt; display:flex; gap:2mm; align-items:center; margin-bottom:.8mm; }}
.on {{ background:var(--orange); width:5mm; height:5mm; font-size:7.5pt; }}
.cs {{ color:var(--muted); }} .ys {{ margin:.6mm 0; }} .tip {{ color:var(--teal); font-weight:600; font-size:8pt; }}
table.finder {{ width:100%; border-collapse:collapse; font-size:8.4pt; }}
.finder th {{ background:var(--navy); color:#fff; text-align:left; padding:1.3mm 2mm; }}
.finder td {{ padding:1.2mm 2mm; border-bottom:1px solid #e1e7ec; }} .finder tr:nth-child(even) td {{ background:var(--light); }}
.do li::marker {{ content:"\\2714  "; color:var(--green); }} .dont li::marker {{ content:"\\2716  "; color:var(--red); }}
footer {{ position:absolute; bottom:5mm; left:10mm; right:10mm; font-size:7pt; color:var(--muted); display:flex; justify-content:space-between; border-top:1px solid #e1e7ec; padding-top:1.5mm; }}
</style></head><body>

<section class="page">
<header><div><h1>PB Health <span>Hospital</span></h1><div class="sub">{html.escape(d['subtitle'])} &middot; Page 1: Master Pitch Script</div></div>
<div class="tag">Policybazaar's own multispeciality hospital<br>Internal use - telesales</div></header>
{strip_html}
<h2>The 30-second pitch</h2>
<div class="hook"><div class="lbl">Say it like this</div><p>{hook['hinglish']}</p><p class="en">{html.escape(hook['english'])}</p>
</div>

<div class="cols">
<div><h2>The 5 pillars of the PB Story</h2>{pillars}
<h2>When to pitch</h2><div class="box"><ul>{when}</ul></div></div>
<div><h2>Where it is</h2>{_where_cards()}
<h2>What PB customers get</h2><div class="box perks"><ul>{perks}</ul></div></div>
</div>
<div class="close"><b>CLOSE:</b> {html.escape(d['close'])}</div>
<div class="score">{html.escape(d['scorecard_note'])}</div>
<footer><span>PB Health Hospital &middot; Pitch Card v2 &middot; {today}</span><span>1 / 2</span></footer>
</section>

<section class="page">
<header><div><h1>Objection <span>Battlecards</span></h1><div class="sub">Page 2: Word-for-word counters &amp; quick reference</div></div>
<div class="tag">Listen &rarr; Acknowledge &rarr; Answer &rarr; Move on</div></header>
<div class="objgrid">{objections}
<div class="obj" style="border-top-color:var(--teal)"><div class="oh"><span class="on" style="background:var(--teal)">&#10003;</span>The 3-step recovery</div>
<div class="ys">1. <b>Acknowledge</b>: "Bilkul sahi sawal hai."<br>2. <b>Answer with the pillar</b> that kills the doubt (MG Road, OT/critical care, salaried doctors).<br>3. <b>Bridge to action</b>: "Main location WhatsApp kar deta hoon."</div></div>
</div>
<div class="cols" style="margin-top:2mm; grid-template-columns:1fr 1fr">
<div><h2>Approved facts</h2>
<table class="finder"><tr><th>Topic</th><th>Say only this</th></tr>{finder}</table></div>
<div class="cols3" style="align-content:start">
<div><h2>Do</h2><div class="box"><ul class="do">{dos}</ul></div></div>
<div><h2>Don't</h2><div class="box"><ul class="dont">{donts}</ul></div></div>
</div></div>
<footer><span>Confirm cashless status for the customer's insurer live before promising. Facts approved by PB Health strategy, Oct 2026.</span><span>2 / 2</span></footer>
</section>
</body></html>"""


# --------------------------------------------------------------------------- #
# PDF renderer (ReportLab - no browser required)
# --------------------------------------------------------------------------- #
def render_pdf(path: str, strip: str | None = None) -> None:
    """Two A4 pages. Each page's type scale is auto-fitted so content fills the
    page without spilling onto a third one."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer,
                                    Table, TableStyle)

    C = {k: colors.HexColor(v) for k, v in BRAND.items()}
    W, H = A4
    M = 10 * mm
    HEADER_H = 22 * mm
    FULL_W = W - 2 * M
    TOP_PAD, BOTTOM = 4 * mm, 11 * mm
    AVAIL_H = H - HEADER_H - TOP_PAD - BOTTOM
    GAP = 5 * mm

    def esc(s: str) -> str:
        return html.escape(s, quote=False)

    class Kit:
        """Style factory bound to a font scale."""

        def __init__(self, k: float):
            self.k = k
            self.body = self.S(8.4)
            self.small = self.S(7.4, color=C["muted"])
            self.h2 = self.S(10, "Helvetica-Bold", C["navy"], before=5, after=2.5)
            self.hook = self.S(9.8)
            self.hook_en = self.S(7.9, "Helvetica-Oblique", C["muted"])
            self.say = self.S(7.9, "Helvetica-Oblique", C["orange"])
            self.pt = self.S(8.9, "Helvetica-Bold", C["navy"])
            self.white = self.S(9, color=colors.white)
            self.objh = self.S(9.2, "Helvetica-Bold", C["navy"])
            self.tip = self.S(7.7, "Helvetica-Bold", C["teal"])
            self.th = self.S(8.4, "Helvetica-Bold", colors.white)

        def S(self, size, font="Helvetica", color=None, before=0, after=0):
            k = self.k
            return ParagraphStyle(f"s{size}{font}{k}", fontName=font, fontSize=size * k, leading=size * k * 1.25,
                                  textColor=color or C["ink"], spaceBefore=before * k, spaceAfter=after * k)

        def h(self, t):
            return Paragraph(f'<font color="{BRAND["teal"]}">|</font> {esc(t.upper())}', self.h2)

        def box(self, flowables, bg, border=None, pad=5):
            p = pad * self.k
            t = Table([[flowables]])
            st = [("BACKGROUND", (0, 0), (-1, -1), bg), ("LEFTPADDING", (0, 0), (-1, -1), p),
                  ("RIGHTPADDING", (0, 0), (-1, -1), p), ("TOPPADDING", (0, 0), (-1, -1), p - 1),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), p)]
            if border is not None:
                st.append(("BOX", (0, 0), (-1, -1), 1.1, border))
            t.setStyle(TableStyle(st))
            return t

        def bullets(self, items, marker="&#8226;", color=None):
            col = color or BRAND["teal"]
            return [Paragraph(f'<font color="{col}">{marker}</font> {esc(i)}', self.body) for i in items]

        def numbered(self, n, title, rest, color):
            d = 5.5 * mm * min(self.k, 1.3)
            badge = Table([[Paragraph(f"<b>{n}</b>", ParagraphStyle("n", textColor=colors.white, fontSize=8 * self.k,
                                                                     leading=9 * self.k, alignment=1))]],
                          colWidths=[d], rowHeights=[d])
            badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                       *[(s, (0, 0), (-1, -1), 0) for s in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")]]))
            t = Table([[badge, [Paragraph(esc(title), self.pt), *rest]]], colWidths=[d + 2 * mm, None])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2 * self.k),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * self.k),
                                   ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd8df"))]))
            return t

    def columns(left, right, lw_frac=0.55):
        lw = (FULL_W - GAP) * lw_frac
        t = Table([[left, "", right]], colWidths=[lw, GAP, FULL_W - GAP - lw])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               *[(s, (0, 0), (-1, -1), 0) for s in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")]]))
        return t

    def page1(kit: Kit) -> list:
        hook = DECK["hook"]
        out = []
        if strip:
            out += [kit.box([Paragraph(esc(strip), kit.small)], colors.HexColor("#FFF8E1"), colors.HexColor("#F5C451"), 3),
                    Spacer(1, 2)]
        out.append(kit.h("The 30-second pitch"))
        out.append(kit.box([
            Paragraph(f'<font color="{BRAND["orange"]}"><b>SAY IT LIKE THIS</b></font>', kit.small),
            Paragraph(hook["hinglish"], kit.hook), Spacer(1, 2 * kit.k), Paragraph(esc(hook["english"]), kit.hook_en),
        ], colors.HexColor("#FFF1E6"), C["orange"], 6))
        left = [kit.h("The 5 pillars of the PB Story")]
        left += [kit.numbered(i, t, [Paragraph(esc(d), kit.body), Paragraph(esc(s), kit.say)], C["teal"])
                 for i, (t, d, s) in enumerate(DECK["pillars"], 1)]
        left += [kit.h("When to pitch"), kit.box(kit.bullets(hook["when"]), C["light"])]
        right = [kit.h("Where it is")]
        right += [kit.numbered(i, w, [], C["navy"]) for i, w in enumerate(DECK["where"], 1)]
        right += [kit.h("What PB customers get"),
                  kit.box(kit.bullets(DECK["family_perks"], color=BRAND["green"]), colors.HexColor("#EAF7EF"), C["green"])]
        out.append(columns(left, right))
        out.append(Spacer(1, 5 * kit.k))
        out.append(kit.box([Paragraph(f'<font color="{BRAND["teal"]}"><b>CLOSE:</b></font> {esc(DECK["close"])}',
                                      kit.white)], C["navy"], None, 6))
        out.append(Spacer(1, 3 * kit.k))
        out.append(Paragraph(esc(DECK["scorecard_note"]), kit.small))
        return out

    def page2(kit: Kit) -> list:
        cards = []
        for i, (t, cs, ys, tip) in enumerate(DECK["objections"], 1):
            cards.append(kit.box([
                Paragraph(f'<font color="{BRAND["orange"]}">{i}.</font> {esc(t)}', kit.objh),
                Paragraph(f'<font color="{BRAND["muted"]}"><b>Customer:</b> {esc(cs)}</font>', kit.body),
                Paragraph(f"<b>You:</b> {esc(ys)}", kit.body),
                Paragraph("&gt; " + esc(tip), kit.tip)], colors.white, colors.HexColor("#cfd8df"), 5))
        cards.append(kit.box([
            Paragraph(f'<font color="{BRAND["teal"]}" name="ZapfDingbats">4</font> The 3-step recovery', kit.objh),
            Paragraph('1. <b>Acknowledge</b>: "Bilkul sahi sawal hai."', kit.body),
            Paragraph("2. <b>Answer with the pillar</b> that kills the doubt (MG Road, OT/critical care, salaried doctors).", kit.body),
            Paragraph('3. <b>Bridge to action</b>: "Main location WhatsApp kar deta hoon."', kit.body)],
            C["light"], C["teal"], 5))
        cw = (FULL_W - GAP) / 2
        grid = Table([[cards[i], "", cards[i + 1]] for i in range(0, len(cards), 2)], colWidths=[cw, GAP, cw])
        grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * kit.k)]))
        lw = (FULL_W - GAP) * 0.58
        rows = [[Paragraph("Topic", kit.th), Paragraph("Say only this", kit.th)]]
        rows += [[Paragraph(f"<b>{esc(a)}</b>", kit.body), Paragraph(esc(b), kit.body)] for a, b in FACTS]
        ft = Table(rows, colWidths=[lw * 0.28, lw * 0.72])
        ft.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C["navy"]),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C["light"]]),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2.5 * kit.k),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * kit.k),
                                ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#e1e7ec"))]))
        right = [kit.h("Do"), kit.box(kit.bullets(DECK["dos"], '<font name="ZapfDingbats">4</font>', BRAND["green"]), C["light"]),
                 kit.h("Don't"), kit.box(kit.bullets(DECK["donts"], '<font name="ZapfDingbats">8</font>', BRAND["red"]), C["light"])]
        return [grid, columns([kit.h("Approved facts"), ft], right, 0.58)]

    def height(flowables) -> float:
        return sum(f.wrap(FULL_W, AVAIL_H * 3)[1] + f.getSpaceBefore() + f.getSpaceAfter() for f in flowables)

    def fit(builder) -> list:
        best = builder(Kit(0.8))
        k = 0.8
        while k <= 1.6:
            fl = builder(Kit(k))
            if height(fl) > AVAIL_H * 0.985:
                break
            best = builder(Kit(k))  # fresh flowables (wrap() caches state)
            k += 0.02
        return best

    titles = {1: ("PB Health Hospital", f"{DECK['subtitle']}  -  Page 1: Master Pitch Script",
                  "Policybazaar's own multispeciality hospital"),
              2: ("Objection Battlecards", "Page 2: Word-for-word counters & quick reference",
                  "Listen > Acknowledge > Answer > Move on")}

    def on_page(canv, doc):
        n = doc.page
        t, sub, tag = titles.get(n, titles[2])
        canv.saveState()
        canv.setFillColor(C["navy"])
        canv.rect(0, H - HEADER_H, W, HEADER_H, stroke=0, fill=1)
        canv.setFillColor(C["orange"])
        canv.rect(0, H - HEADER_H - 1.3 * mm, W, 1.3 * mm, stroke=0, fill=1)
        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-Bold", 18)
        canv.drawString(M, H - 12 * mm, t)
        canv.setFont("Helvetica", 9)
        canv.drawString(M, H - 18 * mm, sub)
        canv.setFont("Helvetica", 7.5)
        canv.drawRightString(W - M, H - 12 * mm, tag)
        canv.drawRightString(W - M, H - 16 * mm, "Internal use - telesales")
        canv.setFillColor(C["muted"])
        canv.setFont("Helvetica", 6.8)
        foot = (f"PB Health Hospital - Pitch Card v2 - {date.today():%d %b %Y}" if n == 1 else
                "Confirm cashless status for the customer's insurer live before promising. Facts approved by PB Health strategy, Oct 2026.")
        canv.drawString(M, 6 * mm, foot)
        canv.drawRightString(W - M, 6 * mm, f"{n} / 2")
        canv.restoreState()

    frame = Frame(M, BOTTOM, FULL_W, AVAIL_H, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(path, pagesize=A4, title="PB Health Hospital - Telesales Pitch Card", author="PB Health Strategy")
    doc.addPageTemplates([PageTemplate("p", frames=[frame], onPage=on_page)])
    doc.build(fit(page1) + [PageBreak()] + fit(page2))


def generate(with_baseline: bool = False, pdf: bool = True) -> dict[str, str]:
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    strip = baseline_strip() if with_baseline else None
    out = {}
    html_path = config.OUTPUT_DIR / "PB_Health_Sales_Deck.html"
    html_path.write_text(render_html(strip), encoding="utf-8")
    out["html"] = str(html_path)
    if pdf:
        pdf_path = config.OUTPUT_DIR / "PB_Health_Sales_Deck.pdf"
        render_pdf(str(pdf_path), strip)
        out["pdf"] = str(pdf_path)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate the PB Health 2-page sales deck")
    ap.add_argument("--with-baseline", action="store_true", help="add current KPI strip from pb_health.db")
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args()
    for kind, p in generate(a.with_baseline, not a.no_pdf).items():
        print(f"{kind.upper()}: {p}")
