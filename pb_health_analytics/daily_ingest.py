"""
Daily T-1 ingestion - run from cron / Windows Task Scheduler.

    python daily_ingest.py                 # yesterday
    python daily_ingest.py --date 2026-10-14
    python daily_ingest.py --backfill 3    # last 3 days (idempotent; skips calls already stored)

Example crontab (07:15 every morning, after the previous day's calls are indexed):
    15 7 * * * cd /path/to/pb_health_analytics && /path/to/venv/bin/python daily_ingest.py >> logs/cron.log 2>&1
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta

import config
from analyzer import ingest_range


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest one day (default: yesterday) into pb_health.db")
    ap.add_argument("--date", help="YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--backfill", type=int, default=1, help="number of days ending at --date")
    ap.add_argument("--demo", action="store_true", help="synthetic data (offline testing)")
    args = ap.parse_args(argv)

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_DIR / "daily_ingest.log")])
    end = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today() - timedelta(days=1)
    start = end - timedelta(days=args.backfill - 1)
    try:
        stats = ingest_range(start, end, mode="daily", demo=args.demo,
                             progress=lambda p, m: logging.info("[%3d%%] %s", int(p * 100), m))
    except Exception as exc:
        logging.error("Daily ingestion failed: %s", exc)
        return 1
    logging.info("Daily ingestion %s -> %s: %s", start, end, stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
