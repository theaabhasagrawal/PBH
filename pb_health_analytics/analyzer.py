"""
Historical baseline diagnostic + reusable ingestion engine.

Examples
--------
    # One-time baseline over the last 21 days (real portal, office network)
    python analyzer.py --days 21

    # Explicit range
    python analyzer.py --from 2026-09-15 --to 2026-10-14

    # Offline demo (synthetic data, no network)
    python analyzer.py --demo --days 21

    # Just re-print the executive summary from what is already in the DB
    python analyzer.py --summary-only

Outputs
-------
* SQLite DB  : data/pb_health.db  (calls, call_analysis, transcripts, daily_denominator, ingestion_runs)
* JSON report: output/baseline_report.json
* Terminal   : Executive Diagnostic Summary
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Callable

import config
import db
import metrics
from classifier import classify_call

log = logging.getLogger("pb.analyzer")
ProgressFn = Callable[[float, str], None]


def _noop(_: float, __: str) -> None:
    pass


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
def ingest_range(start: date, end: date, mode: str = "baseline", demo: bool = False,
                 force: bool = False, max_calls: int | None = None,
                 progress: ProgressFn = _noop, db_path=None) -> dict:
    """Search -> fetch transcripts -> classify -> store, for start..end inclusive.

    Already-classified calls are skipped unless force=True, so the function is
    idempotent and safe to re-run (e.g. by cron)."""
    with db.connect(db_path) as conn:
        run_id = db.start_run(conn, "demo" if demo else mode, start.isoformat(), end.isoformat())
        found = analyzed = 0
        try:
            if demo:
                found, analyzed = _ingest_demo(conn, start, end, force, progress)
            else:
                found, analyzed = _ingest_portal(conn, start, end, mode, force, max_calls, progress)
            db.finish_run(conn, run_id, found, analyzed, "success")
            progress(1.0, f"Done: {analyzed} new calls analysed ({found} found)")
            return {"run_id": run_id, "found": found, "analyzed": analyzed, "status": "success"}
        except Exception as exc:  # record the failure, then surface it
            log.exception("Ingestion failed")
            db.finish_run(conn, run_id, found, analyzed, "failed", f"{type(exc).__name__}: {exc}")
            conn.commit()
            raise


def _ingest_portal(conn, start: date, end: date, mode: str, force: bool,
                   max_calls: int | None, progress: ProgressFn) -> tuple[int, int]:
    from api_client import PortalClient  # imported lazily so demo mode needs no network deps

    client = PortalClient()
    client.login()
    progress(0.02, "Logged in. Searching calls…")

    hits = client.search_calls(start, end)
    found = len(hits)
    done = set() if force else db.existing_call_ids(conn)
    todo = [h for h in hits.values() if h.call_id not in done]
    if max_calls:
        todo = todo[:max_calls]
    log.info("%d calls found, %d to fetch", found, len(todo))
    progress(0.2, f"{found} calls found, fetching {len(todo)} transcripts…")

    analyzed = 0
    with ThreadPoolExecutor(max_workers=config.TRANSCRIPT_WORKERS) as pool:
        futures = {pool.submit(client.get_transcript, h.call_id): h for h in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            h = futures[fut]
            try:
                t = fut.result()
            except Exception as exc:
                log.warning("Transcript %s failed: %s", h.call_id, exc)
                continue
            result = classify_call(h.call_id, [t["english"], t["hindi"]], metadata_city=h.city)
            meta = {
                "call_id": h.call_id, "call_ts": h.call_date, "call_date": (h.call_date or "")[:10],
                "agent_id": h.agent_id, "agent_name": h.agent_name, "team": h.team, "manager": h.manager,
                "city": h.city, "state": h.state, "talktime": h.talktime, "lead_id": h.lead_id,
                "matched_terms": h.matched_terms, "audio_url": t["audio_url"], "source": mode,
            }
            db.upsert_call(conn, meta, result.to_dict(), t["english"], t["hindi"])
            analyzed += 1
            if i % 25 == 0:
                conn.commit()
                progress(0.2 + 0.7 * i / max(len(todo), 1), f"Classified {i}/{len(todo)}")

    progress(0.92, "Fetching PPR denominators…")
    day = start
    while day <= end:
        n, method = client.count_qualified_ncr_calls(day)
        db.set_denominator(conn, day.isoformat(), n, method)
        day += timedelta(days=1)
    return found, analyzed


def _ingest_demo(conn, start: date, end: date, force: bool, progress: ProgressFn) -> tuple[int, int]:
    import demo_data

    done = set() if force else db.existing_call_ids(conn)
    per_day: dict[str, int] = {}
    found = analyzed = 0
    for meta, english in demo_data.generate(start, end):
        found += 1
        d = meta["call_ts"][:10]
        per_day[d] = per_day.get(d, 0) + 1
        if meta["call_id"] in done:
            continue
        res = classify_call(meta["call_id"], [english], metadata_city=meta["city"])
        db.upsert_call(conn, meta, res.to_dict(), english, [])
        analyzed += 1
    for d, n in per_day.items():
        db.set_denominator(conn, d, demo_data.demo_denominator(n, int(d.replace("-", ""))), "demo")
    progress(0.95, f"Generated {found} demo calls")
    return found, analyzed


def reclassify_all(db_path=None) -> int:
    """Re-run the classifier over stored transcripts (after tuning patterns) - no portal calls."""
    import json as _json
    with db.connect(db_path) as conn:
        rows = conn.execute("""SELECT c.call_id, c.city, c.call_ts, c.call_date, c.agent_id, c.agent_name, c.team,
                                      c.manager, c.state, c.talktime, c.lead_id, c.matched_terms, c.audio_url,
                                      c.source, t.english, t.hindi
                               FROM calls c JOIN transcripts t USING(call_id)""").fetchall()
        for r in rows:
            english, hindi = _json.loads(r["english"] or "[]"), _json.loads(r["hindi"] or "[]")
            res = classify_call(r["call_id"], [english, hindi], metadata_city=r["city"])
            meta = dict(r)
            meta["matched_terms"] = _json.loads(r["matched_terms"] or "[]")
            db.upsert_call(conn, meta, res.to_dict(), english, hindi)
    return len(rows)


def purge_demo(db_path=None) -> int:
    with db.connect(db_path) as conn:
        ids = [r[0] for r in conn.execute("SELECT call_id FROM calls WHERE source='demo'")]
        for table in ("call_analysis", "transcripts", "calls"):
            conn.execute(f"DELETE FROM {table} WHERE call_id IN (SELECT call_id FROM calls WHERE source='demo')"
                         if table != "calls" else "DELETE FROM calls WHERE source='demo'")
        conn.execute("DELETE FROM daily_denominator WHERE method='demo'")
    return len(ids)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def build_report(start: date | None = None, end: date | None = None, db_path=None) -> dict:
    df = db.load_calls(db_path)
    denoms = db.load_denominators(db_path)
    if not df.empty and start and end:
        df = df[(df["call_date"] >= str(start)) & (df["call_date"] <= str(end))]
    if df.empty:
        return {"empty": True}
    den = metrics.denominator_for(df, denoms)
    k = metrics.kpi_summary(df, den)
    return {
        "generated_at": db.now(),
        "period": {"from": str(df["call_date"].min().date()), "to": str(df["call_date"].max().date())},
        "contains_demo_data": bool((df["source"] == "demo").any()),
        "kpis": k,
        "pillar_compliance": metrics.pillar_compliance(df).to_dict("records"),
        "location_share": metrics.location_share(df).to_dict("records"),
        "region_gap": metrics.region_gap(df).to_dict("records"),
        "objections": metrics.objection_taxonomy(df).to_dict("records"),
        "top_agents": metrics.agent_leaderboard(df).head(10).to_dict("records"),
        "bottom_agents": metrics.agent_leaderboard(df).tail(10).to_dict("records"),
    }


def print_summary(rep: dict) -> None:
    if rep.get("empty"):
        print("No analysed calls in the database yet. Run an ingestion first.")
        return
    k = rep["kpis"]
    line = "=" * 74
    print(f"\n{line}\n  PB HEALTH HOSPITAL - PITCH EXECUTIVE DIAGNOSTIC SUMMARY")
    print(f"  Period: {rep['period']['from']} -> {rep['period']['to']}   Generated: {rep['generated_at']}")
    if rep["contains_demo_data"]:
        print("  !! CONTAINS SYNTHETIC DEMO DATA - NOT A REAL BASELINE !!")
    print(line)
    print(f"  Calls analysed ................. {k['calls_analyzed']:>8,}")
    print(f"  Calls where agent pitched ...... {k['calls_pitched']:>8,}")
    print(f"  Pitch Penetration Rate (PPR) ... {k['ppr_pct']:>7.1f}%   (denominator {k['ppr_denominator']:,}: {k['ppr_basis']})")
    print(f"  Story Adherence Score .......... {k['story_adherence']:>7.1f} / 100 (pitched calls)")
    print(f"  PB Health App push rate ........ {k['app_push_pct']:>7.1f}%")
    print(f"  Customer objection rate ........ {k['objection_rate_pct']:>7.1f}%")
    print(f"  Most-pitched hub ............... {k['top_location']:>8}")

    print("\n  PILLAR COMPLIANCE (% of pitched calls)")
    for p in rep["pillar_compliance"]:
        bar = "#" * int(p["compliance_pct"] / 4)
        tag = f"{p['weight']:>2} pts" if p["scored"] else "track"
        print(f"   {p['label']:<34} {tag}  {p['compliance_pct']:>5.1f}% {bar}")

    print("\n  LOCATION SHARE (share of all hub mentions)")
    for loc in rep["location_share"]:
        bar = "#" * int(loc["share_pct"] / 4)
        print(f"   {loc['label']:<40} {loc['share_pct']:>5.1f}% ({loc['mentions']:>4}) {bar}")

    if rep["region_gap"]:
        print("\n  NEAREST-HUB GAP (customer region known, pitched calls)")
        for g in rep["region_gap"]:
            print(f"   Customers nearest {g['nearest_hub']:<12} n={g['calls']:>4}  nearest hub named "
                  f"{g['nearest_hub_named_pct']:>5.1f}%   any hub named {g['any_hub_named_pct']:>5.1f}%")

    print("\n  OBJECTION TAXONOMY (% of calls where hospital came up)")
    for o in rep["objections"]:
        print(f"   {o['label']:<42} {o['pct_of_calls']:>5.1f}% ({o['calls']})")

    # Auto-generated headline findings
    print("\n  KEY FINDINGS")
    for f in headline_findings(rep):
        print(f"   - {f}")
    print(line + "\n")


def headline_findings(rep: dict) -> list[str]:
    k, out = rep["kpis"], []
    pillars = {p["pillar"]: p["compliance_pct"] for p in rep["pillar_compliance"]}
    ls = {x["hub"]: x["share_pct"] for x in rep["location_share"]}
    weakest = min((p for p in rep["pillar_compliance"] if p["scored"]), key=lambda p: p["compliance_pct"])
    out.append(f"Only {k['ppr_pct']}% of qualified calls carry a PB Hospital pitch." if k["ppr_basis"].startswith("qualified")
               else f"{k['ppr_pct']}% of hospital-mention calls had an agent-led pitch (true PPR needs the NCR denominator).")
    out.append(f"Weakest scored pillar: {weakest['label']} ({weakest['compliance_pct']}% of pitches).")
    gurgaon = ls.get("IFFCO Chowk", 0) + ls.get("Sector 62", 0)
    out.append(f"Gurgaon hubs take {gurgaon:.0f}% of location mentions; Noida {ls.get('Noida', 0):.0f}%, "
               f"Faridabad {ls.get('Faridabad', 0):.0f}%, Rohini {ls.get('Rohini', 0):.0f}%.")
    for g in rep["region_gap"]:
        if g["nearest_hub"] in ("Noida", "Faridabad", "Rohini") and g["calls"] >= 5 and g["nearest_hub_named_pct"] < 50:
            out.append(f"Customers nearest {g['nearest_hub']} heard their nearest hub only {g['nearest_hub_named_pct']}% of the time.")
    if rep["objections"] and rep["objections"][0]["calls"]:
        out.append(f"Top objection: {rep['objections'][0]['label']} ({rep['objections'][0]['pct_of_calls']}% of calls).")
    if pillars.get("app", 100) < 30:
        out.append(f"PB Health App is pushed on just {pillars['app']}% of pitches - the cheapest lift available.")
    return out


def save_report(rep: dict) -> str:
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.OUTPUT_DIR / "baseline_report.json"
    path.write_text(json.dumps(rep, indent=2, default=str, ensure_ascii=False))
    return str(path)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PB Health pitch baseline diagnostic")
    ap.add_argument("--days", type=int, default=21, help="look-back window ending yesterday (default 21)")
    ap.add_argument("--from", dest="date_from", help="YYYY-MM-DD (overrides --days)")
    ap.add_argument("--to", dest="date_to", help="YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--demo", action="store_true", help="use synthetic data instead of the portal")
    ap.add_argument("--force", action="store_true", help="re-classify calls already in the DB")
    ap.add_argument("--max-calls", type=int, help="cap number of transcripts fetched (smoke tests)")
    ap.add_argument("--summary-only", action="store_true", help="skip ingestion; print summary from DB")
    ap.add_argument("--purge-demo", action="store_true", help="delete all synthetic demo rows and exit")
    ap.add_argument("--reclassify", action="store_true", help="re-run classifier on stored transcripts (no portal calls)")
    args = ap.parse_args(argv)

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_DIR / "analyzer.log")])

    if args.purge_demo:
        print(f"Removed {purge_demo()} demo calls.")
        return 0
    if args.reclassify:
        print(f"Re-classified {reclassify_all()} stored calls.")
        args.summary_only = True

    end = datetime.strptime(args.date_to, "%Y-%m-%d").date() if args.date_to else date.today() - timedelta(days=1)
    start = datetime.strptime(args.date_from, "%Y-%m-%d").date() if args.date_from else end - timedelta(days=args.days - 1)

    if not args.summary_only:
        log.info("Ingesting %s -> %s (%s)", start, end, "demo" if args.demo else "portal")
        stats = ingest_range(start, end, mode="baseline", demo=args.demo, force=args.force,
                             max_calls=args.max_calls,
                             progress=lambda p, m: log.info("[%3d%%] %s", int(p * 100), m))
        log.info("Ingestion: %s", stats)

    rep = build_report(None if args.summary_only else start, None if args.summary_only else end)
    print_summary(rep)
    if not rep.get("empty"):
        print(f"Report saved to {save_report(rep)}")
        print(f"Database: {config.DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
