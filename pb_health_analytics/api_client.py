"""
Authenticated client for the PB Data Science portal API.

Features
--------
* Logs in once and keeps the `ai_portal_cookie` inside a `requests.Session`;
  transparently re-logs in on 401/403.
* Client-side rate limiting + exponential-backoff retries for 429 / 5xx /
  connection errors.
* 504 / read-timeout guard: a search window that times out is automatically
  split in half (down to MIN_SPLIT_WINDOW_HOURS) and both halves are retried.
* Date ranges are always queried in small chunks (SEARCH_CHUNK_DAYS) and
  paginated.

The response schema of the search endpoint is parsed defensively (several
common key names are tried). Run `python api_client.py --probe 2026-10-14` once
on the office network to dump raw JSON samples to ./output/probe_*.json if you
ever need to adjust the parsers.
"""
from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Iterator

import requests

import config

log = logging.getLogger("pb.api")


class PortalError(RuntimeError):
    pass


class GatewayTimeout(PortalError):
    """Raised for HTTP 504 / read timeouts - the caller should shrink the window."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _pick(d: dict, *keys: str, default: Any = None) -> Any:
    """Return the first non-empty value among `keys` (case-insensitive)."""
    if not isinstance(d, dict):
        return default
    lower = {k.lower(): v for k, v in d.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v not in (None, "", []):
            return v
    return default


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def iter_windows(start: date, end: date, chunk_days: int = config.SEARCH_CHUNK_DAYS) -> Iterator[tuple[datetime, datetime]]:
    """Yield [from, to] datetime windows of at most `chunk_days` covering start..end inclusive."""
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=chunk_days - 1), end)
        yield (datetime.combine(cur, datetime.min.time()),
               datetime.combine(chunk_end, datetime.max.time()).replace(microsecond=0))
        cur = chunk_end + timedelta(days=1)


@dataclass
class SearchHit:
    call_id: str
    call_date: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    team: str | None = None
    manager: str | None = None
    city: str | None = None
    state: str | None = None
    talktime: float | None = None
    lead_id: str | None = None
    matched_terms: set[str] = field(default_factory=set)
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_row(cls, row: dict, term: str | None = None) -> "SearchHit | None":
        cid = _pick(row, "callDataId", "call_data_id", "callId", "call_id", "id", "_id")
        if cid is None:
            return None
        call_date = _pick(row, "recordingCallDate", "recording_call_date", "callDate", "call_date", "createdAt", "date")
        hit = cls(
            call_id=str(cid),
            call_date=str(call_date)[:19] if call_date else None,
            agent_id=_str(_pick(row, "agentId", "agent_id", "employeeId", "empId", "agentCode")),
            agent_name=_str(_pick(row, "agentName", "agent_name", "employeeName", "agent")),
            team=_str(_pick(row, "team", "teamName", "team_name", "sub_bu", "subBu")),
            manager=_str(_pick(row, "manager", "managerName", "team_lead", "teamLead", "assistant_manager")),
            city=_str(_pick(row, "city", "customerCity", "customer_city")),
            state=_str(_pick(row, "state", "customerState", "customer_state")),
            talktime=_num(_pick(row, "talktime", "talkTime", "talk_time", "duration")),
            lead_id=_str(_pick(row, "leadId", "lead_id", "LeadID")),
            raw=row,
        )
        if term:
            hit.matched_terms.add(term)
        return hit


def _str(v: Any) -> str | None:
    return None if v is None else str(v).strip() or None


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_rows(payload: Any) -> list[dict]:
    """Find the list of call rows inside an arbitrary search response."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "result", "results", "rows", "hits", "calls", "records", "items", "docs"):
        v = payload.get(key)
        if isinstance(v, list):
            return [r for r in v if isinstance(r, dict)]
        if isinstance(v, dict):
            inner = extract_rows(v)
            if inner:
                return inner
    return []


def extract_total(payload: Any) -> int | None:
    """Find a 'total hits' counter inside an arbitrary search response."""
    if not isinstance(payload, dict):
        return None
    for key in ("total", "totalCount", "total_count", "count", "totalRecords", "totalHits", "total_hits", "totalCalls"):
        v = payload.get(key)
        if isinstance(v, dict):  # elastic style {"value": n}
            v = v.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
    for key in ("data", "result", "hits", "meta", "pagination"):
        v = payload.get(key)
        if isinstance(v, dict):
            t = extract_total(v)
            if t is not None:
                return t
    return None


def build_search_payload(
    terms: Iterable[str],
    date_from: datetime,
    date_to: datetime,
    categories: list[int] | None = None,
    city: list[str] | None = None,
    state: list[str] | None = None,
) -> dict:
    terms = list(terms)
    return {
        "searchKeywords": [
            {
                "search_phrase": t,
                "similar_words": [
                    {"text": t, "speaker": "both", "source": "exect_phrase", "delete": False, "is_repeated": False}
                ],
            }
            for t in terms
        ],
        "searchCategories": categories if categories is not None else [config.PB_HEALTH_CATEGORY_ID],
        "leadId": "", "callDataId": "", "agentId": "",
        "productId": config.PRODUCT_ID_HEALTH,
        "salesandservice": config.SALES_AND_SERVICE_SALES,
        "speaker": "BOTH",
        "talktimeGte": config.MIN_TALKTIME_SECS,
        "talktimeLte": "", "callingType": "", "operation": "OR", "negative_search": False,
        "city": city or [], "state": state or [], "sub_bu": "", "team": "", "manager": "",
        "assistant_manager": "", "team_lead": "", "call_language": "", "category": "",
        "qa_parameter": "", "leadOrigin": "", "wpmLte": "", "searchSummaryFlag": False,
        "recordingCallDateFrom": _fmt(date_from),
        "recordingCallDateTo": _fmt(date_to),
    }


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
class PortalClient:
    def __init__(self, username: str | None = None, password: str | None = None,
                 session: requests.Session | None = None):
        self.username = username or config.PORTAL_USERNAME
        self.password = password or config.PORTAL_PASSWORD
        self.session = session or requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": config.PORTAL_URL,
            "Referer": config.PORTAL_URL + "/",
        })
        self._lock = threading.Lock()
        self._last_request_ts = 0.0
        self._logged_in = False

    # ---------------- auth ----------------
    def login(self) -> None:
        if not self.username or not self.password:
            raise PortalError(
                "Portal credentials missing. Set PB_PORTAL_USERNAME / PB_PORTAL_PASSWORD "
                "in pb_health_analytics/.env (see .env.example)."
            )
        resp = self.session.post(
            config.LOGIN_URL,
            json={"username": self.username, "password": self.password},
            timeout=config.REQUEST_TIMEOUT_SECS,
        )
        if resp.status_code >= 400:
            raise PortalError(f"Login failed: HTTP {resp.status_code} {resp.text[:200]}")
        token = resp.cookies.get(config.AUTH_COOKIE_NAME) or self.session.cookies.get(config.AUTH_COOKIE_NAME)
        if not token:
            raise PortalError(f"Login succeeded but cookie '{config.AUTH_COOKIE_NAME}' was not returned.")
        self.session.cookies.set(config.AUTH_COOKIE_NAME, token)
        self._logged_in = True
        log.info("Logged in to portal as %s", self.username)

    def _ensure_login(self) -> None:
        if not self._logged_in:
            self.login()

    # ---------------- transport ----------------
    def _throttle(self) -> None:
        with self._lock:
            wait = config.MIN_SECONDS_BETWEEN_REQUESTS - (time.monotonic() - self._last_request_ts)
            if wait > 0:
                time.sleep(wait)
            self._last_request_ts = time.monotonic()

    def _post(self, url: str, payload: dict, params: dict | None = None,
              raise_on_504: bool = False) -> Any:
        """POST with retry/backoff. If raise_on_504, a 504/read-timeout raises
        GatewayTimeout immediately (after one retry) so the caller can split the window."""
        self._ensure_login()
        relogged = False
        timeouts = 0
        for attempt in range(config.MAX_RETRIES + 1):
            self._throttle()
            try:
                resp = self.session.post(url, json=payload, params=params, timeout=config.REQUEST_TIMEOUT_SECS)
            except requests.exceptions.ReadTimeout as exc:
                timeouts += 1
                if raise_on_504 and timeouts >= 2:
                    raise GatewayTimeout(str(exc)) from exc
                self._backoff(attempt, f"read timeout: {exc}")
                continue
            except requests.exceptions.ConnectionError as exc:
                self._backoff(attempt, f"connection error: {exc}")
                continue

            if resp.status_code in (401, 403) and not relogged:
                log.warning("Auth rejected (%s) - re-logging in", resp.status_code)
                self._logged_in = False
                self.login()
                relogged = True
                continue
            if resp.status_code == 504:
                timeouts += 1
                if raise_on_504 and timeouts >= 2:
                    raise GatewayTimeout(f"504 for {payload.get('recordingCallDateFrom')} -> {payload.get('recordingCallDateTo')}")
                self._backoff(attempt, "HTTP 504")
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                self._backoff(attempt, f"HTTP {resp.status_code}", float(retry_after) if retry_after and retry_after.isdigit() else None)
                continue
            if resp.status_code >= 400:
                raise PortalError(f"HTTP {resp.status_code} from {url}: {resp.text[:300]}")
            try:
                return resp.json()
            except ValueError as exc:
                raise PortalError(f"Non-JSON response from {url}: {resp.text[:200]}") from exc
        if raise_on_504 and timeouts:
            raise GatewayTimeout(f"Gave up after {timeouts} timeouts")
        raise PortalError(f"Gave up on {url} after {config.MAX_RETRIES + 1} attempts")

    @staticmethod
    def _backoff(attempt: int, reason: str, override: float | None = None) -> None:
        delay = override if override is not None else config.BACKOFF_BASE_SECS * (2 ** attempt)
        log.warning("%s - retrying in %.1fs (attempt %d/%d)", reason, delay, attempt + 1, config.MAX_RETRIES + 1)
        time.sleep(delay)

    # ---------------- search ----------------
    def search_window(self, terms: list[str], date_from: datetime, date_to: datetime,
                      categories: list[int] | None = None, city: list[str] | None = None,
                      state: list[str] | None = None) -> tuple[list[dict], int | None]:
        """Paginate one window. On 504, split the window in half and recurse.
        Returns (rows, total_reported_by_api_or_None)."""
        payload = build_search_payload(terms, date_from, date_to, categories, city, state)
        rows: list[dict] = []
        total: int | None = None
        page_size: int | None = None
        prev_ids: list | None = None
        try:
            for page in range(1, config.MAX_PAGES_PER_WINDOW + 1):
                data = self._post(config.SEARCH_URL, payload, params={"page": page}, raise_on_504=True)
                page_rows = extract_rows(data)
                if page == 1:
                    total = extract_total(data)
                    page_size = len(page_rows)
                if not page_rows:
                    break
                ids = [_pick(r, "callDataId", "call_data_id", "callId", "id", "_id") for r in page_rows]
                if ids == prev_ids:  # API ignored the page param - stop instead of looping
                    break
                prev_ids = ids
                rows.extend(page_rows)
                if total is not None and len(rows) >= total:
                    break
                if page_size and len(page_rows) < page_size:  # short page = last page
                    break
            return rows, total
        except GatewayTimeout:
            span = date_to - date_from
            if span <= timedelta(hours=config.MIN_SPLIT_WINDOW_HOURS):
                log.error("Window %s -> %s still timing out at minimum size; skipping", date_from, date_to)
                return rows, total
            mid = date_from + span / 2
            mid = mid.replace(microsecond=0)
            log.warning("504 on %s -> %s; splitting at %s", date_from, date_to, mid)
            left_rows, left_total = self.search_window(terms, date_from, mid, categories, city, state)
            right_rows, right_total = self.search_window(terms, mid + timedelta(seconds=1), date_to, categories, city, state)
            t = (left_total or 0) + (right_total or 0) if (left_total is not None or right_total is not None) else None
            return left_rows + right_rows, t

    def search_calls(self, start: date, end: date, terms: list[str] | None = None,
                     per_term: bool = True) -> dict[str, SearchHit]:
        """Search all keyword clusters over start..end, chunked by SEARCH_CHUNK_DAYS.

        per_term=True issues one query per term so each hit records *which*
        phrase matched (more requests, but richer data). Results are de-duplicated
        by call id."""
        if terms is None:
            terms = [t for cluster in config.KEYWORD_CLUSTERS.values() for t in cluster]
        hits: dict[str, SearchHit] = {}
        groups = [[t] for t in terms] if per_term else [terms]
        for w_from, w_to in iter_windows(start, end):
            for group in groups:
                rows, _ = self.search_window(group, w_from, w_to)
                for row in rows:
                    h = SearchHit.from_row(row, term=group[0] if per_term else None)
                    if h is None:
                        continue
                    if h.call_id in hits:
                        hits[h.call_id].matched_terms |= h.matched_terms
                    else:
                        hits[h.call_id] = h
            log.info("Window %s -> %s: %d unique calls so far", w_from.date(), w_to.date(), len(hits))
        return hits

    def count_qualified_ncr_calls(self, day: date) -> tuple[int | None, str]:
        """PPR denominator: all qualified (health, sales, >2min) NCR calls for a day.

        Uses an unfiltered keyword query restricted to NCR states and reads the
        total counter. Returns (count, method)."""
        w_from = datetime.combine(day, datetime.min.time())
        w_to = datetime.combine(day, datetime.max.time()).replace(microsecond=0)
        try:
            payload = build_search_payload([], w_from, w_to, categories=[], state=config.NCR_STATES)
            data = self._post(config.SEARCH_URL, payload, params={"page": 1}, raise_on_504=True)
            total = extract_total(data)
            if total is not None:
                return total, "api_total"
        except (PortalError, GatewayTimeout) as exc:
            log.warning("Denominator query failed for %s: %s", day, exc)
        return None, "unavailable"

    # ---------------- transcript ----------------
    def get_transcript(self, call_id: str | int) -> dict:
        """Return {'english': [...turns], 'hindi': [...turns], 'audio_url': str|None, 'raw': {...}}."""
        try:
            cid: Any = int(call_id)
        except (TypeError, ValueError):
            cid = call_id
        data = self._post(config.TRANSCRIPT_URL, {"id": cid, "searchkeywords": [], "searchCategories": []})
        return parse_transcript_response(data)


def parse_transcript_response(data: Any) -> dict:
    result = data
    if isinstance(data, dict):
        for key in ("result", "data"):
            if isinstance(data.get(key), dict):
                result = data[key]
                break
    result = result if isinstance(result, dict) else {}

    def turns(key_options: tuple[str, ...]) -> list[dict]:
        raw = _pick(result, *key_options, default=[]) or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                return []
        out = []
        for t in raw if isinstance(raw, list) else []:
            if not isinstance(t, dict):
                continue
            spk = str(_pick(t, "speakerId", "speaker", "speaker_id", default="")).lower()
            spk = "agent" if spk.startswith("agent") else "customer" if spk.startswith("cust") else spk or "unknown"
            out.append({
                "speakerId": spk,
                "time": _pick(t, "time", default=""),
                "timeStamp": _pick(t, "timeStamp", "timestamp", default=None),
                "text": str(_pick(t, "text", "transcript", default="")),
            })
        return out

    audio_url = None
    audio = _pick(result, "audioUrls", "audio_urls")
    if isinstance(audio, dict):
        comb = audio.get("combinedAudio") or audio.get("combined_audio")
        audio_url = comb.get("url") if isinstance(comb, dict) else comb
    return {
        "english": turns(("englishTranscript", "english_transcript")),
        "hindi": turns(("hindiTranscript", "hindi_transcript")),
        "audio_url": audio_url,
        "raw_keys": sorted(result.keys()),
    }


# --------------------------------------------------------------------------- #
# CLI: connectivity probe
# --------------------------------------------------------------------------- #
def _probe(day: str) -> None:
    """Dump raw responses so parsers can be verified against the live schema."""
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = PortalClient()
    client.login()
    d = datetime.strptime(day, "%Y-%m-%d")
    payload = build_search_payload(["pb health"], d, d.replace(hour=23, minute=59, second=59))
    raw = client._post(config.SEARCH_URL, payload, params={"page": 1})
    (config.OUTPUT_DIR / "probe_search.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False)[:2_000_000])
    rows = extract_rows(raw)
    print(f"search: {len(rows)} rows on page 1, total={extract_total(raw)}")
    if rows:
        print("first row keys:", sorted(rows[0].keys()))
        hit = SearchHit.from_row(rows[0])
        if hit:
            t = client._post(config.TRANSCRIPT_URL, {"id": int(hit.call_id) if hit.call_id.isdigit() else hit.call_id,
                                                     "searchkeywords": [], "searchCategories": []})
            (config.OUTPUT_DIR / "probe_transcript.json").write_text(json.dumps(t, indent=2, ensure_ascii=False)[:2_000_000])
            parsed = parse_transcript_response(t)
            print(f"transcript: {len(parsed['english'])} english turns, {len(parsed['hindi'])} hindi turns, "
                  f"audio={'yes' if parsed['audio_url'] else 'no'}")
    n, method = client.count_qualified_ncr_calls(d.date())
    print(f"denominator (qualified NCR calls): {n} via {method}")
    print(f"Raw JSON saved under {config.OUTPUT_DIR}/probe_*.json")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="PB portal API client utilities")
    ap.add_argument("--probe", metavar="YYYY-MM-DD", help="log in, run one search + transcript, dump raw JSON")
    args = ap.parse_args()
    if args.probe:
        _probe(args.probe)
    else:
        ap.print_help()
