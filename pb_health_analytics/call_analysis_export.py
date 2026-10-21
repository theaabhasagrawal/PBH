"""
PB Health Hospital - real call analysis -> Excel.

    python call_analysis_export.py                 # fetch (resumable) + analyse + write Excel
    python call_analysis_export.py --fetch-only    # just pull search hits + transcripts into the cache
    python call_analysis_export.py --skip-fetch    # re-analyse what is already cached (no portal calls)

Stage 1 (fetch): one OR query per phrase cluster below, one day at a time,
category 10693, and caches the hits and full transcripts in
data/call_export_cache.db. Re-runs skip finished (cluster, day) searches and
already-downloaded transcripts.

Stage 2 (analyse): call_facts.py turns each transcript into plain facts and
workbook.py writes output/PB_Health_Call_Analysis.xlsx. Every number in the
workbook is a count of calls - nothing is weighted or scored.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import config

log = logging.getLogger("pb.export")

SEARCH_TERMS: dict[str, list[str]] = {
    "brand": ["pb health", "pb hospital", "policybazaar hospital", "pb health hospital"],
    "hinglish": ["khud ka hospital", "apna hospital", "humara hospital"],
    "hubs": ["iffco chowk", "sector 62", "golf course", "faridabad", "sector 2",
             "noida sector 50", "sector 50", "rohini"],
}
TERM_CLUSTER = {t: c for c, terms in SEARCH_TERMS.items() for t in terms}
CACHE_PATH = config.BASE_DIR / "data" / "call_export_cache.db"
XLSX_PATH = config.BASE_DIR / "output" / "PB_Health_Call_Analysis.xlsx"

SCHEMA = """
CREATE TABLE IF NOT EXISTS hits (
    call_id    TEXT PRIMARY KEY,
    call_ts    TEXT,
    agent_id   TEXT,
    city       TEXT,
    state      TEXT,
    talktime   REAL,
    lead_id    TEXT,
    terms      TEXT,      -- JSON list of search phrases that matched
    source     TEXT       -- JSON of the raw _source row
);
CREATE TABLE IF NOT EXISTS search_done (
    term TEXT, day TEXT, api_total INTEGER, rows INTEGER, done_at TEXT,
    PRIMARY KEY (term, day)
);
CREATE TABLE IF NOT EXISTS gaps (       -- search windows the portal never answered
    cluster TEXT, w_from TEXT, w_to TEXT, noted_at TEXT,
    PRIMARY KEY (cluster, w_from)
);
CREATE TABLE IF NOT EXISTS transcripts (
    call_id TEXT PRIMARY KEY,
    hindi   TEXT,
    english TEXT,
    fetched_at TEXT
);
"""


def cache_connect(path: Path = CACHE_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # a long read (e.g. building the workbook) must not block the fetcher
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class _GapRecorder(logging.Handler):
    """api_client gives up on a window that still times out at the minimum split
    size and only logs it - its rows are silently missing. Capture those windows
    (with the cluster the logging thread was searching) so they can be retried
    and, if still missing, reported in the workbook."""

    RX = re.compile(r"Window (\S+ \S+) -> (\S+ \S+) still timing out")

    def __init__(self) -> None:
        super().__init__()
        self.ctx = threading.local()
        self.gaps: list[tuple[str, str, str]] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        m = self.RX.search(record.getMessage())
        if m:
            with self._lock:
                self.gaps.append((getattr(self.ctx, "cluster", "?"), m.group(1), m.group(2)))


# --------------------------------------------------------------------------- #
# Stage 1 - fetch
# --------------------------------------------------------------------------- #
def _store_hits(conn: sqlite3.Connection, term: str, rows: list[dict]) -> int:
    from api_client import SearchHit

    n = 0
    for row in rows:
        h = SearchHit.from_row(row, term=term)
        if h is None:
            continue
        src = dict(row.get("_source")) if isinstance(row.get("_source"), dict) else {}
        src["_highlight"] = row.get("highlight")
        old = conn.execute("SELECT terms FROM hits WHERE call_id=?", (h.call_id,)).fetchone()
        terms = sorted(set(json.loads(old["terms"]) if old else []) | {term})
        conn.execute(
            """INSERT INTO hits(call_id, call_ts, agent_id, city, state, talktime, lead_id, terms, source)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(call_id) DO UPDATE SET terms=excluded.terms""",
            (h.call_id, h.call_date, h.agent_id, h.city, h.state, h.talktime, h.lead_id,
             json.dumps(terms), json.dumps(src, ensure_ascii=False, default=str)),
        )
        n += 1
    return n


def fetch(start: date, end: date, workers: int, search_workers: int, conn: sqlite3.Connection) -> None:
    from api_client import PortalClient

    client = PortalClient()
    client.login()
    today = date.today()

    # --- searches: one OR query per (cluster, day), newest day first; today is always re-run.
    # (Per-phrase parallel queries overloaded the portal - every request hit the 60s timeout.)
    done = {(r["term"], r["day"]) for r in conn.execute("SELECT term, day FROM search_done")}
    tasks = []
    d = end
    while d >= start:
        for cluster in SEARCH_TERMS:
            if (cluster, d.isoformat()) not in done or d >= today:
                tasks.append((cluster, d))
        d -= timedelta(days=1)
    log.info("Search: %d (cluster, day) queries to run, %d already cached", len(tasks), len(done))
    recorder = _GapRecorder()
    logging.getLogger("pb.api").addHandler(recorder)

    def run_search(cluster: str, day: date):
        recorder.ctx.cluster = cluster
        # Four 6-hour windows per day: the portal re-runs the whole query for every
        # 50-row page, so full-day windows with 5-6 pages kept hitting 504s.
        rows: list[dict] = []
        total = 0
        for h in range(0, 24, 6):
            w_from = datetime.combine(day, datetime.min.time()) + timedelta(hours=h)
            w_to = w_from + timedelta(hours=6) - timedelta(seconds=1)
            part, t = client.search_window(SEARCH_TERMS[cluster], w_from, w_to)
            rows += part
            total += t or 0
        return rows, total

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=search_workers) as pool:
        futs = {pool.submit(run_search, cluster, day): (cluster, day) for cluster, day in tasks}
        for i, fut in enumerate(as_completed(futs), 1):
            cluster, day = futs[fut]
            try:
                rows, total = fut.result()
            except Exception as exc:  # leave it un-marked so a re-run retries it
                log.warning("Search failed for %r on %s: %s", cluster, day, exc)
                continue
            n = _store_hits(conn, cluster, rows)
            conn.execute("INSERT OR REPLACE INTO search_done VALUES (?,?,?,?,?)",
                         (cluster, day.isoformat(), total, n, _now()))
            conn.commit()
            uniq = conn.execute("SELECT COUNT(*) FROM hits").fetchone()[0]
            log.info("Search %d/%d: %s %s -> %d rows (api total %s) | %.0fs | %d unique calls cached",
                     i, len(tasks), day, cluster, n, total, time.time() - t0, uniq)

    # --- gaps: windows skipped above (or in earlier runs) get one more try each
    for cluster, w_from, w_to in recorder.gaps:
        conn.execute("INSERT OR IGNORE INTO gaps VALUES (?,?,?,?)", (cluster, w_from, w_to, _now()))
    conn.commit()
    pending = [tuple(r) for r in conn.execute("SELECT cluster, w_from, w_to FROM gaps ORDER BY w_from")]
    if pending:
        log.info("Gaps: retrying %d skipped search windows", len(pending))
    for cluster, w_from, w_to in pending:
        # retry in 1-hour pieces: the skipped windows are the busiest hours of the day
        lo, hi = datetime.fromisoformat(w_from), datetime.fromisoformat(w_to)
        still: list[tuple[datetime, datetime]] = []
        got = 0
        while lo <= hi:
            piece_to = min(lo + timedelta(hours=1) - timedelta(seconds=1), hi)
            before = len(recorder.gaps)
            recorder.ctx.cluster = cluster
            try:
                rows, _ = client.search_window(SEARCH_TERMS[cluster], lo, piece_to)
                got += _store_hits(conn, cluster, rows)
                if len(recorder.gaps) != before:
                    still.append((lo, piece_to))
            except Exception as exc:
                log.warning("Gap piece %s %s still failing: %s", cluster, lo, exc)
                still.append((lo, piece_to))
            conn.commit()
            lo = piece_to + timedelta(seconds=1)
        conn.execute("DELETE FROM gaps WHERE cluster=? AND w_from=?", (cluster, w_from))
        for a, b in still:
            conn.execute("INSERT OR IGNORE INTO gaps VALUES (?,?,?,?)", (cluster, _fmt(a), _fmt(b), _now()))
        conn.commit()
        if still:
            log.warning("Gap %s %s -> %s: %d rows recovered, %d hour(s) still missing", cluster, w_from, w_to, got, len(still))
        else:
            log.info("Gap filled: %s %s -> %s, %d rows", cluster, w_from, w_to, got)
    logging.getLogger("pb.api").removeHandler(recorder)

    # --- transcripts: brand / Hinglish hits first, hub-only hits after
    have = {r[0] for r in conn.execute("SELECT call_id FROM transcripts")}
    todo = []
    for r in conn.execute("SELECT call_id, terms FROM hits"):
        if r["call_id"] in have:
            continue
        clusters = set(json.loads(r["terms"]))
        todo.append((0 if clusters & {"brand", "hinglish"} else 1, r["call_id"]))
    todo.sort()
    log.info("Transcripts: %d to fetch, %d already cached", len(todo), len(have))

    t0 = time.time()
    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(client.get_transcript, cid): cid for _, cid in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            cid = futs[fut]
            try:
                t = fut.result()
            except Exception as exc:
                failed += 1
                log.warning("Transcript %s failed: %s", cid, exc)
                continue
            conn.execute("INSERT OR REPLACE INTO transcripts VALUES (?,?,?,?)",
                         (cid, json.dumps(t["hindi"], ensure_ascii=False),
                          json.dumps(t["english"], ensure_ascii=False), _now()))
            if i % 50 == 0 or i == len(todo):
                conn.commit()
                rate = i / max(time.time() - t0, 1e-6)
                log.info("Transcripts %d/%d (%.1f/s, ETA %.0f min, %d failed)", i, len(todo), rate,
                         (len(todo) - i) / max(rate, 1e-6) / 60, failed)
    conn.commit()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PB Health real-call analysis -> Excel")
    ap.add_argument("--days", type=int, default=21, help="look back N days from today, today included (default 21)")
    ap.add_argument("--from", dest="date_from", help="YYYY-MM-DD (overrides --days)")
    ap.add_argument("--to", dest="date_to", help="YYYY-MM-DD (default today)")
    ap.add_argument("--workers", type=int, default=4, help="parallel transcript downloads (default 4)")
    ap.add_argument("--search-workers", type=int, default=2, help="parallel search queries (default 2)")
    ap.add_argument("--rate", type=float, help="min seconds between portal requests (default from config)")
    ap.add_argument("--fetch-only", action="store_true")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--out", default=str(XLSX_PATH))
    args = ap.parse_args(argv)

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_DIR / "call_export.log")])
    if args.rate is not None:
        config.MIN_SECONDS_BETWEEN_REQUESTS = args.rate

    end = datetime.strptime(args.date_to, "%Y-%m-%d").date() if args.date_to else date.today()
    start = datetime.strptime(args.date_from, "%Y-%m-%d").date() if args.date_from else end - timedelta(days=args.days)

    conn = cache_connect()
    if not args.skip_fetch:
        log.info("Fetching %s -> %s", start, end)
        fetch(start, end, args.workers, args.search_workers, conn)
    if args.fetch_only:
        return 0

    import workbook
    return workbook.build(conn, start, end, Path(args.out))


if __name__ == "__main__":
    sys.exit(main())
