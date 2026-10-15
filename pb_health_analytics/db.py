"""SQLite persistence for calls, classifications, denominators and ingestion runs."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    call_id        TEXT PRIMARY KEY,
    call_date      TEXT,            -- YYYY-MM-DD
    call_ts        TEXT,            -- full timestamp if known
    agent_id       TEXT,
    agent_name     TEXT,
    team           TEXT,
    manager        TEXT,
    city           TEXT,
    state          TEXT,
    talktime       REAL,
    lead_id        TEXT,
    matched_terms  TEXT,            -- JSON list of search phrases that hit
    audio_url      TEXT,
    source         TEXT,            -- baseline | daily | demo
    ingested_at    TEXT
);
CREATE TABLE IF NOT EXISTS call_analysis (
    call_id          TEXT PRIMARY KEY REFERENCES calls(call_id),
    pitched          INTEGER,
    any_mention      INTEGER,
    multispeciality  INTEGER,
    location         INTEGER,
    ethical          INTEGER,
    zero_wait        INTEGER,
    app              INTEGER,
    family_discount  INTEGER,
    top_doctors      INTEGER,
    cashless         INTEGER,
    hubs_mentioned   TEXT,          -- JSON list
    customer_region  TEXT,
    nearest_hub      TEXT,
    region_matched   INTEGER,
    adherence_score  REAL,
    has_objection    INTEGER,
    objections       TEXT,          -- JSON list
    snippets         TEXT,          -- JSON {key: [snippets]}
    agent_turns      INTEGER,
    customer_turns   INTEGER,
    classified_at    TEXT
);
CREATE TABLE IF NOT EXISTS transcripts (
    call_id     TEXT PRIMARY KEY REFERENCES calls(call_id),
    english     TEXT,               -- JSON turn list
    hindi       TEXT                -- JSON turn list
);
CREATE TABLE IF NOT EXISTS daily_denominator (
    call_date        TEXT PRIMARY KEY,
    qualified_calls  INTEGER,
    method           TEXT,
    updated_at       TEXT
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mode            TEXT,
    date_from       TEXT,
    date_to         TEXT,
    started_at      TEXT,
    finished_at     TEXT,
    calls_found     INTEGER,
    calls_analyzed  INTEGER,
    status          TEXT,
    message         TEXT
);
CREATE INDEX IF NOT EXISTS idx_calls_date ON calls(call_date);
CREATE INDEX IF NOT EXISTS idx_calls_agent ON calls(agent_id);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect(path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def existing_call_ids(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT call_id FROM call_analysis")}


def upsert_call(conn: sqlite3.Connection, meta: dict, result: dict, english: list, hindi: list) -> None:
    conn.execute(
        """INSERT INTO calls VALUES (:call_id,:call_date,:call_ts,:agent_id,:agent_name,:team,:manager,:city,
               :state,:talktime,:lead_id,:matched_terms,:audio_url,:source,:ingested_at)
           ON CONFLICT(call_id) DO UPDATE SET
               matched_terms=excluded.matched_terms, audio_url=COALESCE(excluded.audio_url, calls.audio_url),
               ingested_at=excluded.ingested_at""",
        {
            "call_id": meta["call_id"], "call_date": (meta.get("call_ts") or "")[:10] or meta.get("call_date"),
            "call_ts": meta.get("call_ts"), "agent_id": meta.get("agent_id"), "agent_name": meta.get("agent_name"),
            "team": meta.get("team"), "manager": meta.get("manager"), "city": meta.get("city"),
            "state": meta.get("state"), "talktime": meta.get("talktime"), "lead_id": meta.get("lead_id"),
            "matched_terms": json.dumps(sorted(meta.get("matched_terms") or [])),
            "audio_url": meta.get("audio_url"), "source": meta.get("source", "baseline"), "ingested_at": now(),
        },
    )
    p = result["pillars"]
    conn.execute(
        """INSERT OR REPLACE INTO call_analysis VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            result["call_id"], int(result["pitched"]), int(result["any_mention"]),
            int(p.get("multispeciality", False)), int(p.get("location", False)), int(p.get("ethical", False)),
            int(p.get("zero_wait", False)), int(p.get("app", False)), int(p.get("family_discount", False)),
            int(p.get("top_doctors", False)), int(p.get("cashless", False)),
            json.dumps(result["hubs_mentioned"]), result["customer_region"], result["nearest_hub"],
            int(result["region_matched"]), result["adherence_score"], int(result["has_objection"]),
            json.dumps(result["objections"]), json.dumps(result["snippets"], ensure_ascii=False),
            result["agent_turns"], result["customer_turns"], now(),
        ),
    )
    conn.execute("INSERT OR REPLACE INTO transcripts VALUES (?,?,?)",
                 (meta["call_id"], json.dumps(english, ensure_ascii=False), json.dumps(hindi, ensure_ascii=False)))


def set_denominator(conn: sqlite3.Connection, call_date: str, n: int | None, method: str) -> None:
    conn.execute("INSERT OR REPLACE INTO daily_denominator VALUES (?,?,?,?)", (call_date, n, method, now()))


def start_run(conn: sqlite3.Connection, mode: str, date_from: str, date_to: str) -> int:
    cur = conn.execute(
        "INSERT INTO ingestion_runs(mode,date_from,date_to,started_at,status) VALUES (?,?,?,?,?)",
        (mode, date_from, date_to, now(), "running"))
    conn.commit()
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, found: int, analyzed: int, status: str, message: str = "") -> None:
    conn.execute(
        "UPDATE ingestion_runs SET finished_at=?, calls_found=?, calls_analyzed=?, status=?, message=? WHERE run_id=?",
        (now(), found, analyzed, status, message[:1000], run_id))


# --------------------------------------------------------------------------- #
# Readers (pandas) used by analyzer + dashboard
# --------------------------------------------------------------------------- #
def load_calls(path: Path | str | None = None) -> pd.DataFrame:
    """One row per analysed call, with JSON columns decoded."""
    with connect(path) as conn:
        df = pd.read_sql_query(
            """SELECT c.*, a.* FROM calls c JOIN call_analysis a USING(call_id)""", conn)
    if df.empty:
        return df
    df = df.loc[:, ~df.columns.duplicated()]
    for col in ("hubs_mentioned", "objections", "matched_terms"):
        df[col] = df[col].apply(lambda s: json.loads(s) if s else [])
    df["snippets"] = df["snippets"].apply(lambda s: json.loads(s) if s else {})
    bool_cols = ["pitched", "any_mention", "region_matched", "has_objection", *config.TRACKED_PILLARS]
    for col in bool_cols:
        df[col] = df[col].fillna(0).astype(bool)
    df["call_date"] = pd.to_datetime(df["call_date"], errors="coerce")
    for col in ("team", "agent_name", "agent_id", "manager", "city"):
        df[col] = df[col].fillna("Unknown")
    return df


def load_denominators(path: Path | str | None = None) -> pd.DataFrame:
    with connect(path) as conn:
        df = pd.read_sql_query("SELECT * FROM daily_denominator", conn)
    if not df.empty:
        df["call_date"] = pd.to_datetime(df["call_date"])
    return df


def load_runs(path: Path | str | None = None) -> pd.DataFrame:
    with connect(path) as conn:
        return pd.read_sql_query("SELECT * FROM ingestion_runs ORDER BY run_id DESC", conn)


def load_transcript(call_id: str, path: Path | str | None = None) -> tuple[list, list]:
    with connect(path) as conn:
        row = conn.execute("SELECT english, hindi FROM transcripts WHERE call_id=?", (call_id,)).fetchone()
    if not row:
        return [], []
    return json.loads(row["english"] or "[]"), json.loads(row["hindi"] or "[]")


def update_audio_url(call_id: str, url: str, path: Path | str | None = None) -> None:
    with connect(path) as conn:
        conn.execute("UPDATE calls SET audio_url=? WHERE call_id=?", (url, call_id))
