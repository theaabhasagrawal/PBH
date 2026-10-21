"""
Keyword rules that flag "PB Hospital was pitched" in the call-tracking tool.

    python keyword_rules.py                     # -> output/sales_kit/PB_Health_Pitch_Keywords.xlsx

Format used by the sales team's tool: each row is a set of keywords that must ALL
appear somewhere in the call (AND); a call is "Pitched" if ANY row matches (OR).

Rules were chosen on half of 15,441 real transcripts and checked on the other half
(see README). "Actually pitched" = the agent named Policybazaar's own hospital
(call_facts.py), which was checked by reading calls.

Inputs: data/call_export_cache.db (transcripts) and data/team_pitch_labels.csv
(the sales team's "Delhi pitch report" labels: call id, TL, AM, Pitched/Not Pitched).
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import call_facts as cf
import config

OUT = config.OUTPUT_DIR / "sales_kit" / "PB_Health_Pitch_Keywords.xlsx"
LABELS = config.BASE_DIR / "data" / "team_pitch_labels.csv"
CACHE = config.BASE_DIR / "data" / "call_export_cache.db"
TOKEN = re.compile(r"[a-z0-9]+")

# The sales team's current rows ("Key words" sheet of the Delhi pitch report, Oct 2026).
CURRENT_ROWS = [
    "discount", "claims, discount", "facility, discount", "claims", "facility", "claims, facility, discount",
    "claims, facility", "top, doctors", "hassle, claims, free", "discount, own, hospital", "top, doctors, discount",
    "perks, discount", "hassle, claims, free, discount", "top, claims, doctors, discount", "top, claims, doctors",
    "claims, own, hospital", "top, doctors, facility, discount", "top, claims, discount", "top, discount",
    "top, doctors, facility", "claims, hospital, own, discount", "top, claims, doctors, facility",
    "free, facility, hassle, claims, discount", "hospital, own, discount", "top, facility, discount",
    "hassle, free, discount", "top, facility, claims, doctors, discount", "own, hospital", "perks, claims, discount",
    "perks, facility, discount", "facility, own, hospital", "hospital, facility, own, discount", "perks, claims",
]

# Recommended: each item is an exact phrase (words next to each other, as the
# speech-to-text writes them - "p b", "m g road").
PHRASE_ROWS = [
    "khud ka hospital", "m g road", "hospital bhi open", "khud ke hospital", "khud ke hospitals", "iffco chowk, open",
    "hospitals bhi open", "apna hospital open", "hospital open ho", "apna hospital bhi", "khud ka ek hospital",
    "khud ka bhi hospital", "p b hospital", "hospital bhi khul", "hospitals open", "p b health care", "own hospital",
    "khud ki hospital", "khud ka on hospital", "hospital khol", "hospital launch", "policy bazaar ka hospital",
    "p b health hospital", "pb health hospital",
]
# Fallback if the tool can only match single words.
WORD_ROWS = ["hospital, gurgaon", "hospital, gurugram", "hospital, khud, iffco"]

PHRASE_NOTES = {
    "khud ka hospital": "Policybazaar ka khud ka hospital (the core line)",
    "m g road": "Location of the open hospital - speech-to-text writes 'm g road'",
    "hospital bhi open": "...ka hospital bhi open ho gaya hai",
    "khud ke hospital": "khud ke hospital bhi khul gaye",
    "iffco chowk, open": "Hospital near IFFCO Chowk + 'open'",
    "p b health hospital": "New script line: 'PB Health Hospital'",
    "pb health hospital": "New script line (alternate spelling)",
    "p b health care": "Agents' variant 'PB Health Care'",
    "apna hospital open": "'apna hospital open kiya' - NOT plain 'apna hospital' (that is the network)",
}


def rows(spec: list[str]) -> list[tuple[str, ...]]:
    return [tuple(x.strip() for x in line.split(",")) for line in spec]


def load_calls(db: Path = CACHE) -> list[dict]:
    labels = {r["call_id"]: r for r in csv.DictReader(open(LABELS))} if LABELS.exists() else {}
    out = []
    conn = sqlite3.connect(db)
    for cid, hi, en in conn.execute("SELECT call_id, hindi, english FROM transcripts"):
        hi, en = json.loads(hi or "[]"), json.loads(en or "[]")
        turns = cf.choose_transcript(hi, en)
        if not turns:
            continue
        toks = TOKEN.findall(" ".join(str(t.get("text") or "") for t in turns).lower())
        f = cf.analyse_call(cid, hi, en)
        out.append({"id": cid, "tokens": set(toks), "seq": " " + " ".join(toks) + " ", "truth": f.pitched,
                    "quote": f.pitch_quote, "team": labels.get(cid),
                    "half": int(hashlib.md5(cid.encode()).hexdigest(), 16) % 2})
    return out


def cell_hit(cell: str, c: dict) -> bool:
    return f" {cell} " in c["seq"] if " " in cell else cell in c["tokens"]


def hit(rule_rows, c) -> bool:
    return any(all(cell_hit(x, c) for x in r) for r in rule_rows)


def score(rule_rows, calls, key=lambda c: c["truth"]) -> dict:
    """rule_rows may also be a function call -> bool (e.g. the tracker's own label)."""
    tp = fp = fn = 0
    for c in calls:
        p = rule_rows(c) if callable(rule_rows) else hit(rule_rows, c)
        t = key(c)
        tp += p and t; fp += p and not t; fn += (not p) and t
    n = len(calls) or 1
    return {"calls": len(calls), "flagged": (tp + fp) / n, "actual": (tp + fn) / n,
            "precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0}


# --------------------------------------------------------------------------- #
# Workbook
# --------------------------------------------------------------------------- #
NAVY, ORANGE, GREY = "01589F", "EA4722", "666666"
THIN = Side(style="thin", color="D9D9D9")


def _hdr(ws, r, labels):
    for i, v in enumerate(labels, 1):
        c = ws.cell(row=r, column=i, value=v)
        c.font = Font(name="Arial", bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor=NAVY)
        c.alignment = Alignment(wrap_text=True, vertical="center")


def _row(ws, r, values, fmts=None, bold=False):
    for i, v in enumerate(values, 1):
        c = ws.cell(row=r, column=i, value=v)
        c.font = Font(name="Arial", bold=bold); c.border = Border(bottom=THIN)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if fmts and fmts.get(i):
            c.number_format = fmts[i]


def _title(ws, text, sub):
    ws["A1"] = text; ws["A1"].font = Font(name="Arial", bold=True, size=14, color=NAVY)
    ws["A2"] = sub; ws["A2"].font = Font(name="Arial", italic=True, color=GREY)


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build(calls: list[dict], out: Path = OUT) -> dict:
    team = [c for c in calls if c["team"]]
    team_test = [c for c in team if c["half"] == 1]
    tracker = lambda c: c["team"]["label"] == "Pitched"
    versions = [("Current tracker (as reported)", tracker),
                ("New - phrase rows (recommended)", rows(PHRASE_ROWS)),
                ("New - word-only rows (fallback)", rows(WORD_ROWS))]
    res = {}
    wb = Workbook()

    # ---- Summary
    ws = wb.active; ws.title = "Summary"
    _title(ws, "PB Hospital pitch tracking - current vs new keywords",
           f"Gurgaon FF team calls from the Delhi pitch report ({len(team):,} calls, 8 Sep - 20 Oct 2026), "
           "checked against what was actually said on each call.")
    _hdr(ws, 4, ["Keyword version", "Calls flagged 'Pitched'", "Actually pitched", "When it says 'Pitched', it is right",
                 "Real pitches it catches", "Rows"])
    r = 5
    for name, rr in versions:
        s = score(rr, team); res[name] = s
        _row(ws, r, [name, s["flagged"], s["actual"], s["precision"], s["recall"], "-" if callable(rr) else len(rr)],
             {2: "0.0%", 3: "0.0%", 4: "0.0%", 5: "0.0%"}, bold=name.startswith("New - phrase"))
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Checked on calls NOT used to pick the rules (held-out half)").font = Font(name="Arial", bold=True)
    r += 1
    _hdr(ws, r, ["Keyword version", "Calls flagged 'Pitched'", "Actually pitched", "When it says 'Pitched', it is right",
                 "Real pitches it catches", "Calls"])
    r += 1
    for name, rr in versions:
        s = score(rr, team_test)
        _row(ws, r, [name, s["flagged"], s["actual"], s["precision"], s["recall"], s["calls"]],
             {2: "0.0%", 3: "0.0%", 4: "0.0%", 5: "0.0%"})
        r += 1
    r += 1
    _hdr(ws, r, ["Month", "Current tracker says", "Actually pitched", "New phrase rows say", "Calls"])
    r += 1
    for label, lo, hi in (("Sep 2026 (8-30)", "2026-09-01", "2026-09-30"), ("Oct 2026 (1-20)", "2026-10-01", "2026-10-31")):
        m = [c for c in team if lo <= c["team"]["date"] <= hi]
        cur = sum(tracker(c) for c in m) / len(m)
        act = sum(c["truth"] for c in m) / len(m)
        new = sum(hit(rows(PHRASE_ROWS), c) for c in m) / len(m)
        _row(ws, r, [label, cur, act, new, len(m)], {2: "0.0%", 3: "0.0%", 4: "0.0%"})
        r += 1
    r += 1
    notes = [
        "Rule format (same as the tool): every keyword in a row must appear somewhere in the call (AND); a call is 'Pitched' if any row matches (OR).",
        "'Actually pitched' = the advisor named Policybazaar's own hospital ('khud ka hospital', 'PB Health hospital', 'policybazaar ka hospital open hua'...). "
        "Words like 'discount', 'claims', 'facility', 'top doctors' are used on almost every insurance call and do not mean the hospital was pitched.",
        "Phrase rows need the tool to match exact phrases (words next to each other). If it can only match single words, use the word-only rows: "
        "less accurate, but still far better than today.",
        "Speech-to-text spellings matter: it writes 'p b health', 'm g road'. Keep the spaces exactly as given.",
        "Accuracy of the 'actually pitched' check: in a hand-read of 15 calls the phrase rows flagged but the check said 'not pitched', 13 were real pitches - "
        "so the phrase rows are, if anything, more accurate than shown.",
        "Rows were picked on half of 15,441 real transcripts and checked on the other half (held-out table above).",
        "'Current tracker' uses the Pitched / Not Pitched labels exactly as reported in the Delhi pitch report.",
    ]
    for n in notes:
        ws.cell(row=r, column=1, value="• " + n).alignment = Alignment(wrap_text=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        ws.row_dimensions[r].height = 30
        r += 1
    _widths(ws, [44, 18, 16, 22, 18, 10])

    # ---- New phrase rows
    def rule_sheet(title, spec, sub):
        ws = wb.create_sheet(title)
        _title(ws, title, sub)
        _hdr(ws, 4, ["#", "Key words (all must appear)", "Keyword 1", "Keyword 2", "Calls it flags", "Of those, really pitched",
                     "Example / what it catches"])
        for i, line in enumerate(spec, 1):
            rr = rows([line])
            m = [c for c in calls if hit(rr, c)]
            prec = sum(c["truth"] for c in m) / len(m) if m else 0
            cells = [x.strip() for x in line.split(",")]
            ex = PHRASE_NOTES.get(line) or next((c["quote"][:140] for c in m if c["truth"] and c["quote"]), "")
            _row(ws, 4 + i, [i, line, cells[0], cells[1] if len(cells) > 1 else "", len(m), prec, ex], {6: "0%"})
        _widths(ws, [5, 28, 22, 14, 14, 18, 70])
        ws.freeze_panes = "A5"

    rule_sheet("New key words - phrases", PHRASE_ROWS,
               "Recommended. Each item is an exact phrase; a comma means AND. Counts are over all 15,441 transcripts.")
    rule_sheet("New key words - words only", WORD_ROWS,
               "Fallback if the tool cannot match phrases. Single words; a comma means AND.")

    # ---- Old keyword audit
    ws = wb.create_sheet("Old key words audit")
    _title(ws, "Why the current list over-counts", f"Each current row, on the {len(team):,} Gurgaon team calls")
    _hdr(ws, 4, ["Current row", "Calls it flags", "% of all calls", "Of those, really pitched"])
    seen = set()
    for i, line in enumerate(CURRENT_ROWS, 5):
        if line in seen:
            continue
        seen.add(line)
        m = [c for c in team if hit(rows([line]), c)]
        _row(ws, i, [line, len(m), len(m) / len(team), (sum(c["truth"] for c in m) / len(m)) if m else 0],
             {3: "0%", 4: "0%"})
    _widths(ws, [42, 14, 14, 22])

    # ---- Team-wise
    ws = wb.create_sheet("TL-wise pitch rate")
    _title(ws, "TL-wise: what the tracker says vs what was actually said", "Gurgaon FF team, 8 Sep - 20 Oct 2026")
    _hdr(ws, 4, ["AM", "TL", "Calls", "Tracker says pitched", "Actually pitched", "New phrase rows say", "Gap (tracker - actual)"])
    groups = defaultdict(list)
    for c in team:
        groups[(c["team"]["am"], c["team"]["tl"])].append(c)
    r = 5
    for (am, tl), m in sorted(groups.items(), key=lambda kv: (kv[0][0] or "", -len(kv[1]))):
        cur = sum(tracker(c) for c in m) / len(m); act = sum(c["truth"] for c in m) / len(m)
        new = sum(hit(rows(PHRASE_ROWS), c) for c in m) / len(m)
        _row(ws, r, [am, tl, len(m), cur, act, new, cur - act], {4: "0%", 5: "0%", 6: "0%", 7: "+0%;-0%"})
        r += 1
    _widths(ws, [22, 24, 9, 18, 16, 18, 18])
    ws.freeze_panes = "A5"

    # ---- Examples
    ws = wb.create_sheet("Examples")
    _title(ws, "Real calls", "What the advisor said, around the words that triggered each flag")
    _hdr(ws, 4, ["Call ID", "Current tracker", "Actually pitched?", "New phrase rows", "What was said"])
    r = 5
    wrong = [c for c in team if tracker(c) and not c["truth"] and "discount" in c["tokens"]][:6]
    caught = [c for c in team if c["truth"] and hit(rows(PHRASE_ROWS), c)][:6]
    missed_old = [c for c in team if c["truth"] and not tracker(c) and hit(rows(PHRASE_ROWS), c)][:4]
    for c in wrong:
        i = c["seq"].find(" discount ")
        _row(ws, r, [int(c["id"]), "Pitched", "No", "Not pitched", "…" + c["seq"][max(0, i - 140): i + 120].strip() + "…"]); r += 1
    for c in caught + missed_old:
        _row(ws, r, [int(c["id"]), c["team"]["label"], "Yes", "Pitched", c["quote"][:260]]); r += 1
    _widths(ws, [14, 16, 16, 16, 110])
    for w in wb.worksheets:
        for row in w.iter_rows():
            for c in row:
                if c.font and c.font.name != "Arial":
                    c.font = Font(name="Arial", bold=c.font.bold, italic=c.font.italic, size=c.font.size, color=c.font.color)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return res


def main() -> int:
    calls = load_calls()
    res = build(calls)
    for name, s in res.items():
        print(f"{name:38} flags {s['flagged']:5.1%} | actual {s['actual']:5.1%} | right {s['precision']:5.1%} | catches {s['recall']:5.1%}")
    print("Saved", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
