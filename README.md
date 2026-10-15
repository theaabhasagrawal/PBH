# PBH – PB Health Hospital Strategy Workspace

This is the central repository for PB Health Hospital strategy work: analytics code, sales enablement material and the reference data files.

| Path | What it is |
|------|------------|
| [`pb_health_analytics/`](pb_health_analytics/README.md) | End-to-end pitch analytics pipeline: portal API client, call classifier, baseline diagnostic, SQLite store, Streamlit dashboard, daily cron ingest and the 2-page sales deck generator |
| [`pb_health_analytics/output/PB_Health_Sales_Deck.pdf`](pb_health_analytics/output/PB_Health_Sales_Deck.pdf) | Print-ready 2-page telesales pitch card and objection battlecards (HTML version alongside) |
| `Final PBH Tariff Complete 29th Sept TPA.xlsb` | PBH tariff (TPA), 29 Sept |
| `Star - ANH package rates.xlsx` | Star Health – ANH package rates |
| `SBI - Quick Info Data Sheet (filled draft).xlsx` | SBI General quick info data sheet (draft) |

## Quick start

```bash
cd pb_health_analytics
pip install -r requirements.txt
cp .env.example .env          # add portal credentials (never commit .env)
python analyzer.py --days 21  # baseline diagnostic (needs PB network)
streamlit run app.py          # dashboard
python deck_generator.py      # regenerate the sales deck
```

To try everything offline with synthetic data, run `python analyzer.py --demo`. For full details, see [`pb_health_analytics/README.md`](pb_health_analytics/README.md).

## Data hygiene

* Credentials live only in `pb_health_analytics/.env`, which is git-ignored.
* The call database (`pb_health_analytics/data/pb_health.db`) holds customer conversations. It is git-ignored and must stay on PB infrastructure.
