# PB Health Hospital – Pitch Analytics Pipeline

This project measures how well telesales agents pitch **PB Health Hospital** on health-insurance sales calls. It has three parts:

| # | Deliverable | Entry point |
|---|-------------|-------------|
| 1 | One-time **historical baseline diagnostic**: pulls calls, classifies pitch and objections, prints an executive summary and stores everything in SQLite | `python analyzer.py --days 21` |
| 2 | **2-page sales reference deck / battlecard** (print-ready HTML + PDF) | `python deck_generator.py` → `output/PB_Health_Sales_Deck.{html,pdf}` |
| 3 | **Interactive daily dashboard**, with a 1-click T-1 ingest and a cron script | `streamlit run app.py` / `python daily_ingest.py` |

---

## 1. Setup (one time)

```bash
cd pb_health_analytics
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # then put the portal username/password in .env
```

> **Credentials:** the code reads them only from `.env` or environment variables, never from source. `.env` is git-ignored, so it can't be committed by accident.

**Network:** `datascienceapi.policybazaar.com` is reachable only from the PB office network or VPN.

Run a quick check on the live API first:

```bash
python api_client.py --probe 2026-10-14
```

This logs in, runs one search, fetches one transcript and asks for the NCR denominator. It prints row counts and the response keys, and saves the raw JSON to `output/probe_*.json`. The parsers already try several common key names. If a field shows up as empty (for example agent name or team), add its key to the `_pick(...)` list in `SearchHit.from_row`.

## 2. Baseline diagnostic

```bash
python analyzer.py --days 21                    # last 21 days ending yesterday
python analyzer.py --from 2026-09-15 --to 2026-10-14
python analyzer.py --max-calls 200 --days 3     # quick smoke test
python analyzer.py --summary-only               # re-print the summary from the DB
```

Pipeline: **search → fetch transcripts → classify → store**.

* **Search.** Every phrase in `config.KEYWORD_CLUSTERS` (brand, Hinglish "apna/khud ka hospital", locations, features) is queried with category `10693`, product 2, sales, talktime > 120s.
  * Queries run in 2-day windows (`PB_SEARCH_CHUNK_DAYS`) and are paginated.
  * On a **504 or read timeout**, the window is split in half and retried, down to 3-hour windows.
  * 429 and 5xx errors get exponential backoff, with client-side rate limiting. A 401 triggers an automatic re-login.
* **Transcripts** are fetched in parallel (4 workers by default). Calls already in the DB are skipped, so re-runs are safe.
* **PPR denominator.** For each day, an NCR-state query (Delhi/Haryana/UP) with no keywords reads the total count of qualified calls.
  * If the portal won't return a count, the KPI clearly falls back to *pitched ÷ hospital-mention calls* and says so.

**Outputs:**

* `data/pb_health.db` (SQLite) with these tables: `calls`, `call_analysis`, `transcripts`, `daily_denominator`, `ingestion_runs`
* `output/baseline_report.json`
* the Executive Diagnostic Summary in the terminal, with auto-generated key findings

## 3. KPI definitions (`metrics.py`)

| KPI | Definition |
|-----|------------|
| **Pitch Penetration Rate** | calls where the **agent** pitched PB Hospital ÷ total qualified NCR sales calls × 100 |
| **Story Adherence Score** (0–100, pitched calls only) | Multispeciality 15, Location 25, Ethical / no overcharging 20, Zero waiting / digital 15, App download 15, Family discount 10 |
| **Location Share %** | Share of agent hub mentions across IFFCO Chowk, Sector 62, Faridabad, Noida and Rohini |
| **Nearest-hub gap** | % of calls where the agent named the hub closest to the customer's detected region |
| **Objection Rate %** | % of hospital-mention calls where the customer raised an objection or doubt |
| **Objection taxonomy** | Location/distance, Clinical trust, Insurance validity, Facility scope, Discount confusion (+ general skepticism) |

Location scoring: naming any hub earns 18 points. Naming the hub nearest the customer adds a 7-point bonus. Customer region comes from the customer's own words, or from the portal's city field if they don't say. Both values are set in `config.py`.

## 4. Classifier (`classifier.py`)

The classifier reads each turn separately:

* `agent` turns are checked against the story pillars and hub names.
* `customer` turns are checked for objections and the customer's home region.

It matches Roman Hinglish, English and Devanagari, and checks both the English and Hindi transcripts. Fuzzier concepts use proximity rules. For example, a word like *door* / *far* only counts as a distance objection when a place name appears within 60 characters. Every flag keeps the verbatim snippet so it can be audited in the dashboard.

**Tuning:** spot-check about 50 real calls in the Transcript Explorer after the first baseline. Then add or remove patterns in `PILLAR_RX` / `OBJECTION_RX` and run `python analyzer.py --reclassify`. This re-scores every stored transcript offline, with no portal calls, and prints the updated summary.

## 5. Sales deck

```bash
python deck_generator.py                  # HTML + PDF
python deck_generator.py --with-baseline  # adds a "where we are today" KPI strip from the DB
```

* **Page 1 – Master Pitch Script:** 20-second hook (Hinglish + English), the 5 PB Story pillars with ready-to-say lines, the 5 NCR hubs with "pitch to" areas, family perks, close and app push, and the scoring rubric.
* **Page 2 – Objection Battlecards:** word-for-word counters to 7 objections (Max/Fortis comparison, distance, existing-policy cashless, clinic vs hospital, discount redemption, app activation, "insurer's own hospital"). Also a 3-step recovery, the hub address finder table, and Do / Don't lists.

All copy lives in the `DECK` dict at the top of `deck_generator.py`. Each PDF page auto-fits its font size to fill exactly one A4 page, and the HTML also prints to exactly 2 pages.

> **Check with PB Health ops before printing:** (1) the exact discount redemption steps in objection #5, and (2) the list of insurers with cashless tie-ups (objection #3 tells agents to confirm live). The deck deliberately gives no discount percentages or prices.

## 6. Dashboard

```bash
streamlit run app.py
```

1. **Executive KPI Summary:** PPR, Story Score, App Push %, Top Location, objection rate and nearest-hub %, each compared with the previous period. Also key findings, pillar and objection charts, and the daily trend.
2. **Location & Pillar Drilldown:** hub bar and donut charts, the nearest-hub gap (this exposes Noida/Faridabad/Rohini under-pitching), a team × pillar heatmap, and an agent leaderboard you can export to CSV.
3. **Transcript Explorer:**
   * filter by team, agent, objection, missing pillar, hub or pitch status, or search by call/lead ID
   * agent vs customer chat view with pitch keywords highlighted, pillar and objection chips, and evidence snippets
   * an audio player for the S3 recording, plus a refresh button for expired pre-signed URLs
4. **Daily Ingestion & Trends:** a ▶ button to ingest T-1, custom-range backfill, run history, and KPI and location-share trends over time.

Sidebar filters: data source, date range, team and agent.

## 7. Daily automation

```bash
python daily_ingest.py                 # yesterday
python daily_ingest.py --backfill 3    # last 3 days (idempotent)
```

crontab (07:15 daily):

```
15 7 * * * cd /path/to/PBH/pb_health_analytics && .venv/bin/python daily_ingest.py >> logs/cron.log 2>&1
```

On Windows, Task Scheduler can run the same command.

## 8. Real call analysis → Excel

```bash
python call_analysis_export.py                  # last 21 days: fetch (resumable) + analyse + write Excel
python call_analysis_export.py --skip-fetch     # re-analyse the cached calls only (no portal calls)
python call_analysis_export.py --from 2026-10-01 --to 2026-10-15
```

Writes `output/PB_Health_Call_Analysis.xlsx` (git-ignored, because it holds verbatim call quotes) and prints a summary in the terminal.

* **Fetch.** One OR query per phrase cluster (brand, Hinglish "khud ka/apna/humara hospital", hub names) per day, with category `10693`, two at a time. Running each phrase as its own parallel query overloaded the portal. Hits and transcripts are cached in `data/call_export_cache.db`, so a re-run only pulls what is missing.
* **Analyse** (`call_facts.py`). This step is separate from `classifier.py` and gives plain yes/no facts, not scores.
  * "PB Health" on its own is **not** counted as a hospital pitch. On real calls it mostly means the PB Health app, wellness programme or membership.
  * Hubs, story elements and doubts are only read in the turns right around a hospital mention.
  * "MG Road, Gurgaon" is kept as its own location bucket, because that is how agents actually describe the open hospital.
* **Workbook** (`workbook.py`) has 4 tabs:
  * Executive Summary
  * Customer Doubts & Objections
  * Pitch Elements Tracker
  * Call-by-Call Master Data

  Every figure on the first three tabs is a `COUNTIFS` over the master tab, so you can filter the master tab to see the calls behind any number. Counter-scripts are taken from `deck_generator.DECK`.

## 9. Sales kit: pitch card, advisor playbook, tracking keywords

```bash
python keyword_rules.py            # PB_Health_Pitch_Keywords.xlsx: new tracker keywords + accuracy vs the current list
python pitch_card.py               # PB_Health_Advisor_Pitch_Card.pdf / .pptx (A4 landscape, PB Health brand)
node advisor_playbook.js           # PB_Health_Advisor_Playbook.docx (needs `npm install docx@9`)
```

All three write to `output/sales_kit/` and read their numbers from `output/sales_kit/stats.json`.

* **Keywords** (`keyword_rules.py`). The sales team's tool marks a call "Pitched" when every word in any one row appears in the call.
  * The current list (`discount`, `claims`, `facility`, ...) flags 65% of Gurgaon calls, but only 42% actually mention the hospital.
  * `PHRASE_ROWS` is the recommended replacement: 93% right when it says "Pitched", and it catches 96% of real pitches. It needs exact-phrase matching. If the tool can only match single words, use `WORD_ROWS` instead.
  * The script tests every version against real transcripts (`data/call_export_cache.db`) and the team's labels (`data/team_pitch_labels.csv`, both git-ignored).
  * The workbook is git-ignored because it contains agent names and call snippets.
* **Pitch card** (`pitch_card.py`). One content block is rendered two ways: as HTML printed to PDF by headless Chrome, and as an editable PowerPoint built at the same geometry.
  * It uses the official logo (`assets/pbh-logo.png`) and brand gradients, with Nunito and DM Sans fonts.
  * PowerPoint shows a fallback font where Nunito and DM Sans aren't installed. The PDF embeds them.
* **Playbook** (`advisor_playbook.js`). A rewrite of the team's advisor guide covering the 30-second script, five pillars with real call excerpts, real customer questions, tracking, a TL call check and approved facts.
* **Facts.** Only MG Road, Gurugram is open. "100% claim guarantee" and "India's only insurance company with its own hospital" were approved by PB Health strategy on 21 Oct 2026. Update `pitch_card.py` and `advisor_playbook.js` together when any fact changes.

## 10. Offline demo mode

`demo_data.py` generates **synthetic** Hinglish calls, skewed toward Gurgaon with a weak app push, so the whole pipeline can be tested without portal access:

```bash
python analyzer.py --demo --days 21    # writes source='demo' rows
streamlit run app.py                   # banner warns that demo data is in view
python analyzer.py --purge-demo        # remove all demo rows before the real baseline
```

## 11. Tests

```bash
python -m pytest -q tests
```

The tests cover: classifier scoring and objections, Devanagari text, Sector-2 disambiguation, 504 window splitting (with a mocked portal), transcript parsing, idempotent ingestion, offline re-classification, the PPR fallback and demo purge.

## Project layout

```
pb_health_analytics/
├── config.py          # API URLs, env-based credentials, keyword clusters, hubs, weights, taxonomy
├── api_client.py      # session/login, rate limit, retry/backoff, 504 window splitting, pagination, transcripts, --probe
├── classifier.py      # turn-by-turn pillar + objection + region classifier with snippets
├── metrics.py         # PPR, Story Adherence, Location Share, nearest-hub gap, objections, trends, leaderboard
├── db.py              # SQLite schema + readers/writers
├── analyzer.py        # baseline diagnostic CLI + reusable ingest_range()
├── daily_ingest.py    # cron T-1 ingestion
├── deck_generator.py  # 2-page sales deck (HTML + ReportLab PDF)
├── app.py             # Streamlit dashboard
├── call_analysis_export.py  # real-call fetch + Excel export CLI
├── call_facts.py      # per-call facts: Hinglish harmonisation, pitch / hub / USP / doubt detection
├── workbook.py        # PB_Health_Call_Analysis.xlsx builder (COUNTIFS over the master tab)
├── keyword_rules.py   # tracker keyword rows (AND within a row, OR across rows) + accuracy workbook
├── pitch_card.py      # one-page advisor pitch card (PDF + editable PPTX)
├── advisor_playbook.js # advisor playbook (.docx, docx-js)
├── assets/            # PB Health logo and brand gradient bars
├── demo_data.py       # synthetic calls for offline testing
├── tests/             # pytest suite
├── output/            # generated deck (committed); reports/probes (ignored)
└── data/              # pb_health.db (ignored – contains customer conversations)
```

> `data/` is git-ignored on purpose, because transcripts contain customer PII. Keep the DB on a PB machine or a shared drive, not in GitHub.
