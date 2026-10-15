"""KPI scorecard functions. All take the DataFrame produced by `db.load_calls()`."""
from __future__ import annotations

from collections import Counter

import pandas as pd

import config


def _pct(num: float, den: float) -> float:
    return round(100.0 * num / den, 1) if den else 0.0


def pitch_penetration(df: pd.DataFrame, qualified_ncr_calls: int | None) -> dict:
    """PPR % = calls where the agent pitched PB Hospital / total qualified NCR sales calls.

    If the denominator is unknown, falls back to "pitched / calls where the
    hospital was mentioned by anyone" and flags it, so the number is never
    silently inflated."""
    pitched = int(df["pitched"].sum()) if not df.empty else 0
    if qualified_ncr_calls:
        return {"ppr": _pct(pitched, qualified_ncr_calls), "pitched": pitched,
                "denominator": int(qualified_ncr_calls), "basis": "qualified NCR sales calls"}
    mention = int(df["any_mention"].sum()) if not df.empty else 0
    return {"ppr": _pct(pitched, mention), "pitched": pitched, "denominator": mention,
            "basis": "fallback: calls with any hospital mention (denominator unavailable)"}


def denominator_for(df: pd.DataFrame, denoms: pd.DataFrame) -> int | None:
    """Sum the stored daily denominators over the dates present in df."""
    if df.empty or denoms is None or denoms.empty:
        return None
    dates = set(df["call_date"].dropna().dt.normalize())
    d = denoms[denoms["call_date"].dt.normalize().isin(dates) & denoms["qualified_calls"].notna()]
    if d.empty or d["call_date"].nunique() < len(dates):
        return None  # partial coverage would distort PPR
    return int(d["qualified_calls"].sum())


def story_adherence(df: pd.DataFrame) -> float:
    p = df[df["pitched"]] if not df.empty else df
    return round(float(p["adherence_score"].mean()), 1) if len(p) else 0.0


def pillar_compliance(df: pd.DataFrame) -> pd.DataFrame:
    """% of pitched calls covering each pillar."""
    p = df[df["pitched"]] if not df.empty else df
    rows = []
    for pillar in config.TRACKED_PILLARS:
        rate = _pct(p[pillar].sum(), len(p)) if len(p) else 0.0
        rows.append({"pillar": pillar, "label": config.PILLAR_LABELS[pillar], "compliance_pct": rate,
                     "weight": config.PILLAR_WEIGHTS.get(pillar, 0), "scored": pillar in config.PILLAR_WEIGHTS})
    return pd.DataFrame(rows)


def location_share(df: pd.DataFrame) -> pd.DataFrame:
    """Share of hub mentions across the 5 hubs (calls mentioning hub / all hub mentions)."""
    counts = Counter(h for hubs in (df["hubs_mentioned"] if not df.empty else []) for h in hubs)
    total = sum(counts.values())
    return pd.DataFrame([
        {"hub": h, "label": config.HUBS[h]["label"], "mentions": counts.get(h, 0),
         "share_pct": _pct(counts.get(h, 0), total)}
        for h in config.HUB_ORDER
    ])


def region_gap(df: pd.DataFrame) -> pd.DataFrame:
    """For pitched calls with a known customer region: how often the nearest hub was named."""
    p = df[df["pitched"] & df["nearest_hub"].notna()] if not df.empty else df
    if p.empty:
        return pd.DataFrame(columns=["nearest_hub", "calls", "nearest_hub_named_pct", "any_hub_named_pct"])
    g = p.groupby("nearest_hub").agg(calls=("call_id", "count"),
                                     matched=("region_matched", "sum"),
                                     any_loc=("location", "sum")).reset_index()
    g["nearest_hub_named_pct"] = (100 * g["matched"] / g["calls"]).round(1)
    g["any_hub_named_pct"] = (100 * g["any_loc"] / g["calls"]).round(1)
    return g[["nearest_hub", "calls", "nearest_hub_named_pct", "any_hub_named_pct"]]


def objection_rate(df: pd.DataFrame) -> float:
    """% of calls (where the hospital came up) in which the customer voiced skepticism."""
    base = df[df["any_mention"]] if not df.empty else df
    return _pct(base["has_objection"].sum(), len(base)) if len(base) else 0.0


def objection_taxonomy(df: pd.DataFrame) -> pd.DataFrame:
    base = df[df["any_mention"]] if not df.empty else df
    counts = Counter(o for objs in (base["objections"] if len(base) else []) for o in objs)
    rows = [{"objection": k, "label": v, "calls": counts.get(k, 0), "pct_of_calls": _pct(counts.get(k, 0), len(base))}
            for k, v in config.OBJECTION_LABELS.items()]
    return pd.DataFrame(rows).sort_values("calls", ascending=False).reset_index(drop=True)


def top_location(df: pd.DataFrame) -> str:
    ls = location_share(df)
    if ls["mentions"].sum() == 0:
        return "-"
    return str(ls.sort_values("mentions", ascending=False).iloc[0]["hub"])


def app_push_rate(df: pd.DataFrame) -> float:
    p = df[df["pitched"]] if not df.empty else df
    return _pct(p["app"].sum(), len(p)) if len(p) else 0.0


def kpi_summary(df: pd.DataFrame, qualified_ncr_calls: int | None = None) -> dict:
    ppr = pitch_penetration(df, qualified_ncr_calls)
    return {
        "calls_analyzed": int(len(df)),
        "calls_pitched": ppr["pitched"],
        "ppr_pct": ppr["ppr"],
        "ppr_denominator": ppr["denominator"],
        "ppr_basis": ppr["basis"],
        "story_adherence": story_adherence(df),
        "app_push_pct": app_push_rate(df),
        "top_location": top_location(df),
        "objection_rate_pct": objection_rate(df),
    }


def daily_trend(df: pd.DataFrame, denoms: pd.DataFrame | None = None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    dmap = {}
    if denoms is not None and not denoms.empty:
        dmap = dict(zip(denoms["call_date"].dt.normalize(), denoms["qualified_calls"]))
    rows = []
    for day, g in df.groupby(df["call_date"].dt.normalize()):
        k = kpi_summary(g, dmap.get(day) if pd.notna(dmap.get(day, None)) else None)
        ls = location_share(g).set_index("hub")["share_pct"].to_dict()
        rows.append({"date": day, **{x: k[x] for x in ("calls_analyzed", "calls_pitched", "ppr_pct",
                                                        "story_adherence", "app_push_pct", "objection_rate_pct")},
                     **{f"share_{h}": ls.get(h, 0.0) for h in config.HUB_ORDER}})
    return pd.DataFrame(rows).sort_values("date")


def agent_leaderboard(df: pd.DataFrame, min_calls: int = 3) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(["team", "agent_name"]).agg(
        calls=("call_id", "count"), pitched=("pitched", "sum"),
        adherence=("adherence_score", lambda s: s[df.loc[s.index, "pitched"]].mean()),
        app_push=("app", "sum"), location=("location", "sum"), objections=("has_objection", "sum"),
    ).reset_index()
    g = g[g["calls"] >= min_calls]
    g["pitch_rate_pct"] = (100 * g["pitched"] / g["calls"]).round(1)
    g["adherence"] = g["adherence"].fillna(0).round(1)
    return g.sort_values(["adherence", "pitch_rate_pct"], ascending=False)
