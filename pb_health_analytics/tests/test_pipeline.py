from datetime import date, datetime

import pytest
import requests

import analyzer
import api_client
import config
import db
import metrics


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setattr(config, "DB_PATH", p)
    return p


def test_demo_ingest_and_kpis(tmp_db):
    stats = analyzer.ingest_range(date(2026, 10, 1), date(2026, 10, 3), demo=True)
    assert stats["analyzed"] > 100
    again = analyzer.ingest_range(date(2026, 10, 1), date(2026, 10, 3), demo=True)
    assert again["analyzed"] == 0  # idempotent
    df = db.load_calls()
    den = metrics.denominator_for(df, db.load_denominators())
    k = metrics.kpi_summary(df, den)
    assert k["ppr_basis"] == "qualified NCR sales calls"
    assert 0 < k["ppr_pct"] < 100 and 0 < k["story_adherence"] <= 100
    assert abs(metrics.location_share(df)["share_pct"].sum() - 100) < 0.5
    rep = analyzer.build_report()
    assert rep["contains_demo_data"] and analyzer.headline_findings(rep)
    assert analyzer.reclassify_all() == len(df)
    assert db.load_calls()["adherence_score"].sum() == df["adherence_score"].sum()
    assert analyzer.purge_demo() == len(df)
    assert db.load_calls().empty


def test_ppr_falls_back_without_denominator(tmp_db):
    analyzer.ingest_range(date(2026, 10, 1), date(2026, 10, 1), demo=True)
    k = metrics.kpi_summary(db.load_calls(), None)
    assert k["ppr_basis"].startswith("fallback")


def test_iter_windows_chunks():
    w = list(api_client.iter_windows(date(2026, 10, 1), date(2026, 10, 5), chunk_days=2))
    assert [(a.day, b.day) for a, b in w] == [(1, 2), (3, 4), (5, 5)]
    assert w[0][1].strftime("%H:%M:%S") == "23:59:59"


class FakeResp:
    def __init__(self, status, data=None):
        self.status_code, self._data, self.headers, self.text = status, data, {}, str(data)
        self.cookies = requests.cookies.RequestsCookieJar()

    def json(self):
        return self._data


class FakeSession(requests.Session):
    """Returns 504 for any window longer than 12h, else one row per window."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def post(self, url, json=None, params=None, timeout=None):
        if url == config.LOGIN_URL:
            r = FakeResp(200, {"ok": True})
            r.cookies.set(config.AUTH_COOKIE_NAME, "tok")
            return r
        f = datetime.strptime(json["recordingCallDateFrom"], "%Y-%m-%d %H:%M:%S")
        t = datetime.strptime(json["recordingCallDateTo"], "%Y-%m-%d %H:%M:%S")
        self.calls.append((f, t, params))
        if (t - f).total_seconds() > 12 * 3600:
            return FakeResp(504)
        if params["page"] > 1:
            return FakeResp(200, {"data": []})
        return FakeResp(200, {"data": [{"callDataId": int(f.timestamp()), "agentName": "A"}], "total": 1})


def test_search_splits_window_on_504(monkeypatch):
    monkeypatch.setattr(config, "BACKOFF_BASE_SECS", 0)
    monkeypatch.setattr(config, "MIN_SECONDS_BETWEEN_REQUESTS", 0)
    client = api_client.PortalClient("u", "p", session=FakeSession())
    hits = client.search_calls(date(2026, 10, 1), date(2026, 10, 2), terms=["pb health"])
    # 2-day window -> two 1-day halves -> four ~12h leaves
    assert len(hits) == 4
    assert all(h.matched_terms == {"pb health"} for h in hits.values())


def test_parse_transcript_response():
    data = {"result": {"englishTranscript": [{"speakerId": "Agent", "time": "0:01", "timeStamp": 1, "text": "hi"}],
                       "hindiTranscript": [], "audioUrls": {"combinedAudio": {"url": "https://s3/x.wav"}}}}
    t = api_client.parse_transcript_response(data)
    assert t["english"][0]["speakerId"] == "agent" and t["audio_url"] == "https://s3/x.wav"
