"""
PB Health Hospital - Pitch Analytics Dashboard

    streamlit run app.py

Pages
  1. Executive KPI Summary
  2. Location & Pillar Drilldown
  3. Transcript Explorer
  4. Daily Ingestion & Trends
"""
from __future__ import annotations

import html
import re
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analyzer
import config
import db
import metrics
from classifier import HIGHLIGHT_RX

st.set_page_config(page_title="PB Health Pitch Analytics", page_icon="🏥", layout="wide")

NAVY, TEAL, ORANGE, RED, GREEN = "#0B2A4A", "#00A3A1", "#F26B21", "#C0392B", "#1E8E5A"
HUB_COLORS = {"IFFCO Chowk": NAVY, "Sector 62": "#3A6EA5", "Faridabad": ORANGE, "Noida": TEAL, "Rohini": "#8E44AD"}

st.markdown(f"""
<style>
.block-container {{ padding-top: 1.6rem; }}
div[data-testid="stMetric"] {{ background: rgba(0,163,161,.07); border: 1px solid rgba(0,163,161,.35);
    border-radius: 10px; padding: 12px 16px; }}
.bubble {{ padding: 8px 12px; border-radius: 12px; margin: 4px 0; max-width: 82%; line-height: 1.4; font-size: .93rem; }}
.agent {{ background: rgba(11,42,74,.08); border-left: 4px solid {NAVY}; }}
.customer {{ background: rgba(242,107,33,.09); border-right: 4px solid {ORANGE}; margin-left: auto; }}
.who {{ font-size: .72rem; opacity: .7; font-weight: 600; }}
mark {{ background: #FFE58F; padding: 0 2px; border-radius: 3px; color: inherit; }}
.demo-banner {{ background: #FFF4E5; border: 1px solid #F5A623; color: #7A4B00; padding: 8px 14px; border-radius: 8px; margin-bottom: 8px; }}
.chip {{ display:inline-block; padding: 2px 9px; margin: 2px 3px 2px 0; border-radius: 12px; font-size: .78rem; }}
.chip.ok {{ background: rgba(30,142,90,.14); color: {GREEN}; }} .chip.no {{ background: rgba(192,57,43,.12); color: {RED}; }}
.chip.obj {{ background: rgba(242,107,33,.15); color: #B4501A; }}
</style>""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=300, show_spinner=False)
def load_all():
    return db.load_calls(), db.load_denominators(), db.load_runs()


def refresh():
    load_all.clear()


calls, denoms, runs = load_all()

st.sidebar.title("🏥 PB Health Pitch Analytics")
page = st.sidebar.radio("Page", ["1 · Executive KPI Summary", "2 · Location & Pillar Drilldown",
                                 "3 · Transcript Explorer", "4 · Daily Ingestion & Trends"])


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filters")
    if df.empty:
        return df
    sources = sorted(df["source"].dropna().unique())
    if len(sources) > 1:
        chosen = st.sidebar.multiselect("Data source", sources, default=[s for s in sources if s != "demo"] or sources)
        df = df[df["source"].isin(chosen)]
    if df.empty:
        return df
    dmin, dmax = df["call_date"].min().date(), df["call_date"].max().date()
    rng = st.sidebar.date_input("Call date range", (max(dmin, dmax - timedelta(days=29)), dmax),
                                min_value=dmin, max_value=dmax)
    if isinstance(rng, tuple) and len(rng) == 2:
        df = df[(df["call_date"].dt.date >= rng[0]) & (df["call_date"].dt.date <= rng[1])]
    teams = sorted(df["team"].unique())
    sel_teams = st.sidebar.multiselect("Team", teams)
    if sel_teams:
        df = df[df["team"].isin(sel_teams)]
    agents = sorted(df["agent_name"].unique())
    sel_agents = st.sidebar.multiselect("Agent", agents)
    if sel_agents:
        df = df[df["agent_name"].isin(sel_agents)]
    return df


df = apply_filters(calls)

if not calls.empty and (calls["source"] == "demo").any() and (df.empty or (df["source"] == "demo").any()):
    st.markdown('<div class="demo-banner">⚠️ <b>Demo data in view.</b> These are synthetic calls for testing the '
                'pipeline offline. Run <code>python analyzer.py</code> on the PB network for the real baseline, '
                'then <code>python analyzer.py --purge-demo</code>.</div>', unsafe_allow_html=True)


def empty_state():
    st.info("No analysed calls yet. Go to **4 · Daily Ingestion & Trends** to pull calls, or run "
            "`python analyzer.py --days 21` (real) / `python analyzer.py --demo` (synthetic).")


def period_delta(cur: pd.DataFrame, full: pd.DataFrame) -> dict | None:
    """KPIs for the same-length period immediately before the current filter window."""
    if cur.empty:
        return None
    start, end = cur["call_date"].min(), cur["call_date"].max()
    span = end - start + pd.Timedelta(days=1)
    prev = full[(full["call_date"] >= start - span) & (full["call_date"] < start)]
    prev = prev[prev["source"].isin(cur["source"].unique())]
    if prev.empty:
        return None
    return metrics.kpi_summary(prev, metrics.denominator_for(prev, denoms))


# --------------------------------------------------------------------------- #
# Page 1 - Executive summary
# --------------------------------------------------------------------------- #
def page_exec():
    st.title("Executive KPI Summary")
    if df.empty:
        return empty_state()
    den = metrics.denominator_for(df, denoms)
    k = metrics.kpi_summary(df, den)
    prev = period_delta(df, calls)

    def delta(key, suffix=""):
        return None if not prev else f"{k[key] - prev[key]:+.1f}{suffix} vs prev. period"

    c = st.columns(4)
    c[0].metric("Pitch Penetration Rate", f"{k['ppr_pct']:.1f}%", delta("ppr_pct", " pts"),
                help=f"{k['calls_pitched']:,} pitched / {k['ppr_denominator']:,} — {k['ppr_basis']}")
    c[1].metric("Story Adherence Score", f"{k['story_adherence']:.1f} / 100", delta("story_adherence"),
                help="Weighted pillar score, averaged over calls where the agent pitched PB Health")
    c[2].metric("App Push %", f"{k['app_push_pct']:.1f}%", delta("app_push_pct", " pts"),
                help="% of pitched calls where the agent asked the customer to download the PB Health app")
    c[3].metric("Top Location Pitched", k["top_location"],
                help=config.HUBS[k["top_location"]]["label"] if k["top_location"] in config.HUBS else None)
    c = st.columns(4)
    c[0].metric("Calls analysed", f"{k['calls_analyzed']:,}")
    c[1].metric("Calls pitched", f"{k['calls_pitched']:,}")
    c[2].metric("Customer objection rate", f"{k['objection_rate_pct']:.1f}%", delta("objection_rate_pct", " pts"),
                delta_color="inverse")
    rg = metrics.region_gap(df)
    match = (rg["nearest_hub_named_pct"] * rg["calls"]).sum() / rg["calls"].sum() if not rg.empty else 0
    c[3].metric("Nearest hub named", f"{match:.1f}%", help="Pitched calls with a known customer region where the agent named the closest hub")
    if not k["ppr_basis"].startswith("qualified"):
        st.caption("ℹ️ PPR denominator unavailable for some days — showing pitched / hospital-mention calls instead.")

    st.markdown("#### Key findings")
    rep = {"kpis": k, "pillar_compliance": metrics.pillar_compliance(df).to_dict("records"),
           "location_share": metrics.location_share(df).to_dict("records"),
           "region_gap": rg.to_dict("records"), "objections": metrics.objection_taxonomy(df).to_dict("records")}
    for f in analyzer.headline_findings(rep):
        st.markdown(f"- {f}")

    left, right = st.columns(2)
    with left:
        pc = metrics.pillar_compliance(df)
        pc = pc[pc["scored"]]
        fig = px.bar(pc, x="compliance_pct", y="label", orientation="h", text="compliance_pct",
                     title="Pillar compliance (% of pitched calls)", color_discrete_sequence=[TEAL])
        fig.update_traces(texttemplate="%{text:.0f}%")
        fig.update_layout(yaxis_title="", xaxis_title="", xaxis_range=[0, 100], height=340, margin=dict(l=0, r=10, t=40, b=0))
        st.plotly_chart(fig, width="stretch")
    with right:
        ot = metrics.objection_taxonomy(df)
        fig = px.bar(ot, x="pct_of_calls", y="label", orientation="h", text="calls",
                     title="Objections (% of calls where hospital came up)", color_discrete_sequence=[ORANGE])
        fig.update_layout(yaxis_title="", xaxis_title="", yaxis_autorange="reversed", height=340, margin=dict(l=0, r=10, t=40, b=0))
        st.plotly_chart(fig, width="stretch")

    tr = metrics.daily_trend(df, denoms)
    if len(tr) > 1:
        fig = go.Figure()
        fig.add_scatter(x=tr["date"], y=tr["ppr_pct"], name="PPR %", line=dict(color=NAVY, width=3))
        fig.add_scatter(x=tr["date"], y=tr["story_adherence"], name="Story score", line=dict(color=TEAL, width=3))
        fig.add_scatter(x=tr["date"], y=tr["app_push_pct"], name="App push %", line=dict(color=ORANGE, width=2, dash="dot"))
        fig.update_layout(title="Daily trend", height=320, margin=dict(l=0, r=10, t=40, b=0), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, width="stretch")


# --------------------------------------------------------------------------- #
# Page 2 - Location & pillar drilldown
# --------------------------------------------------------------------------- #
def page_drill():
    st.title("Location & Pillar Drilldown")
    if df.empty:
        return empty_state()
    ls = metrics.location_share(df)
    a, b = st.columns([1.3, 1])
    with a:
        fig = px.bar(ls, x="hub", y="mentions", color="hub", hover_data=["label"], color_discrete_map=HUB_COLORS, text="share_pct",
                     title="Hub mentions by agents")
        fig.update_traces(texttemplate="%{text:.1f}%")
        fig.update_layout(showlegend=False, xaxis_title="", height=360, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig, width="stretch")
    with b:
        fig = px.pie(ls, names="label", values="mentions", hole=.5, color="hub", color_discrete_map=HUB_COLORS,
                     title="Location share")
        fig.update_layout(height=360, margin=dict(l=0, r=0, t=40, b=0), legend=dict(font=dict(size=10)))
        st.plotly_chart(fig, width="stretch")

    rg = metrics.region_gap(df)
    if not rg.empty:
        st.markdown("#### Nearest-hub gap — did the agent name the hub closest to the customer?")
        m = rg.melt(id_vars=["nearest_hub", "calls"], value_vars=["any_hub_named_pct", "nearest_hub_named_pct"],
                    var_name="measure", value_name="pct")
        m["measure"] = m["measure"].map({"any_hub_named_pct": "Any hub named", "nearest_hub_named_pct": "Nearest hub named"})
        fig = px.bar(m, x="nearest_hub", y="pct", color="measure", barmode="group", text="pct",
                     color_discrete_sequence=["#B0BEC5", TEAL], hover_data=["calls"])
        fig.update_traces(texttemplate="%{text:.0f}%")
        fig.update_layout(xaxis_title="Customer's nearest hub", yaxis_title="% of pitched calls", yaxis_range=[0, 105],
                          height=360, margin=dict(l=0, r=0, t=10, b=0), legend_title="")
        st.plotly_chart(fig, width="stretch")

    st.markdown("#### Pillar compliance by team")
    p = df[df["pitched"]]
    if not p.empty:
        heat = p.groupby("team")[config.TRACKED_PILLARS].mean().mul(100).round(1)
        heat.columns = [config.PILLAR_LABELS[c] for c in heat.columns]
        heat["Story score"] = p.groupby("team")["adherence_score"].mean().round(1)
        fig = px.imshow(heat, text_auto=".0f", aspect="auto", color_continuous_scale=["#FDEDEC", "#FAD7A0", "#A3E4D7", TEAL],
                        zmin=0, zmax=100)
        fig.update_layout(height=120 + 40 * len(heat), margin=dict(l=0, r=0, t=10, b=0), coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")

    st.markdown("#### Agent leaderboard")
    min_calls = st.slider("Minimum calls per agent", 1, 30, 5)
    lb = metrics.agent_leaderboard(df, min_calls)
    if lb.empty:
        st.caption("No agents meet the minimum.")
    else:
        lb = lb.rename(columns={"team": "Team", "agent_name": "Agent", "calls": "Calls", "pitched": "Pitched",
                                "pitch_rate_pct": "Pitch rate %", "adherence": "Story score", "app_push": "App pushes",
                                "location": "Hub named", "objections": "Calls w/ objection"})
        st.dataframe(lb[["Team", "Agent", "Calls", "Pitched", "Pitch rate %", "Story score", "App pushes",
                         "Hub named", "Calls w/ objection"]],
                     width="stretch", hide_index=True,
                     column_config={"Story score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
                                    "Pitch rate %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f")})
        st.download_button("Download leaderboard CSV", lb.to_csv(index=False), "agent_leaderboard.csv", "text/csv")


# --------------------------------------------------------------------------- #
# Page 3 - Transcript explorer
# --------------------------------------------------------------------------- #
def highlight(text: str) -> str:
    spans = []
    for rx in HIGHLIGHT_RX:
        spans += [(m.start(), m.end()) for m in rx.finditer(text) if m.end() > m.start()]
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out, pos = [], 0
    for s, e in merged:
        out.append(html.escape(text[pos:s]))
        out.append(f"<mark>{html.escape(text[s:e])}</mark>")
        pos = e
    out.append(html.escape(text[pos:]))
    return "".join(out)


def render_turns(turns: list[dict]):
    parts = []
    for t in turns:
        who = t.get("speakerId", "unknown")
        cls = "agent" if who == "agent" else "customer"
        parts.append(f'<div class="bubble {cls}"><div class="who">{html.escape(who.upper())} · {html.escape(str(t.get("time", "")))}</div>'
                     f'{highlight(str(t.get("text", "")))}</div>')
    st.markdown("".join(parts) or "<i>No turns.</i>", unsafe_allow_html=True)


def page_explorer():
    st.title("Transcript Explorer")
    if df.empty:
        return empty_state()
    f = st.columns(4)
    pitched_f = f[0].selectbox("Pitch status", ["All", "Pitched", "Not pitched (mention only)"])
    obj_f = f[1].selectbox("Objection", ["Any / none"] + list(config.OBJECTION_LABELS.values()))
    missing_f = f[2].selectbox("Missing pillar", ["—"] + [config.PILLAR_LABELS[p] for p in config.SCORED_PILLARS])
    hub_f = f[3].selectbox("Hub mentioned", ["—"] + config.HUB_ORDER)
    q = st.text_input("Search call id / lead id / agent")

    v = df
    if pitched_f == "Pitched":
        v = v[v["pitched"]]
    elif pitched_f.startswith("Not"):
        v = v[~v["pitched"]]
    if obj_f != "Any / none":
        key = next(k for k, lbl in config.OBJECTION_LABELS.items() if lbl == obj_f)
        v = v[v["objections"].apply(lambda o: key in o)]
    if missing_f != "—":
        key = next(k for k in config.SCORED_PILLARS if config.PILLAR_LABELS[k] == missing_f)
        v = v[v["pitched"] & ~v[key]]
    if hub_f != "—":
        v = v[v["hubs_mentioned"].apply(lambda h: hub_f in h)]
    if q:
        ql = q.lower()
        v = v[v["call_id"].str.lower().str.contains(ql, regex=False) | v["lead_id"].fillna("").str.contains(ql, regex=False)
              | v["agent_name"].str.lower().str.contains(ql, regex=False)]

    st.caption(f"{len(v):,} calls match")
    if v.empty:
        return
    table = v.sort_values(["pitched", "call_ts"], ascending=False)[
        ["call_id", "call_ts", "team", "agent_name", "pitched", "adherence_score", "hubs_mentioned", "customer_region", "objections"]
    ].head(500).copy()
    table["hubs_mentioned"] = table["hubs_mentioned"].apply(", ".join)
    table["objections"] = table["objections"].apply(lambda o: ", ".join(config.OBJECTION_LABELS[x].split(" (")[0] for x in o))
    sel = st.dataframe(table, width="stretch", hide_index=True, height=260, on_select="rerun",
                       selection_mode="single-row",
                       column_config={"adherence_score": st.column_config.ProgressColumn("Story score", min_value=0, max_value=100, format="%.0f")})
    rows = sel.selection.rows if sel and hasattr(sel, "selection") else []
    call_id = table.iloc[rows[0]]["call_id"] if rows else table.iloc[0]["call_id"]
    row = v[v["call_id"] == call_id].iloc[0]

    st.markdown(f"### Call `{call_id}`")
    meta = st.columns([1, 4])
    meta[0].metric("Story score", f"{row['adherence_score']:.0f} / 100")
    talk = int(row["talktime"] or 0)
    meta[1].markdown(
        f"**Agent:** {row['agent_name']} ({row['agent_id']})  \n**Team:** {row['team']} · **Manager:** {row['manager']}  \n"
        f"**Customer region:** {row['customer_region'] or '—'} · **City (portal):** {row['city']} · "
        f"**Talk time:** {talk // 60}m {talk % 60}s · **When:** {row['call_ts']}")

    chips = "".join(f'<span class="chip {"ok" if row[p] else "no"}">{"✔" if row[p] else "✘"} {config.PILLAR_LABELS[p]}</span>'
                    for p in config.TRACKED_PILLARS)
    chips += "".join(f'<span class="chip obj">⚑ {config.OBJECTION_LABELS[o]}</span>' for o in row["objections"])
    if row["hubs_mentioned"]:
        chips += "".join(f'<span class="chip ok">📍 {h}</span>' for h in row["hubs_mentioned"])
    if row["nearest_hub"]:
        chips += f'<span class="chip {"ok" if row["region_matched"] else "no"}">Nearest hub: {row["nearest_hub"]}</span>'
    st.markdown(chips, unsafe_allow_html=True)

    english, hindi = db.load_transcript(call_id)
    a, b = st.columns([1.6, 1])
    with a:
        tabs = st.tabs(["English transcript", "Hindi transcript"])
        with tabs[0]:
            render_turns(english)
        with tabs[1]:
            render_turns(hindi)
    with b:
        st.markdown("**Audio**")
        if row.get("audio_url"):
            st.audio(row["audio_url"])
            st.caption("Pre-signed S3 links expire — use refresh if playback fails.")
        else:
            st.caption("No audio URL stored.")
        if row["source"] != "demo" and st.button("🔄 Refresh audio URL from portal"):
            try:
                from api_client import PortalClient
                t = PortalClient().get_transcript(call_id)
                if t["audio_url"]:
                    db.update_audio_url(call_id, t["audio_url"])
                    refresh()
                    st.rerun()
                else:
                    st.warning("Portal returned no audio URL.")
            except Exception as exc:
                st.error(f"Portal error: {exc}")
        st.markdown("**Evidence snippets**")
        for key, snips in row["snippets"].items():
            label = config.OBJECTION_LABELS.get(key.split(":", 1)[1]) if key.startswith("objection:") else \
                config.PILLAR_LABELS.get(key, "PB Hospital pitch" if key == "pitch" else key)
            with st.expander(label):
                for s in snips:
                    st.markdown(f"> {highlight(s)}", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Page 4 - Daily ingestion & trends
# --------------------------------------------------------------------------- #
def page_ingest():
    st.title("Daily Ingestion & Trends")
    yesterday = date.today() - timedelta(days=1)
    have_creds = bool(config.PORTAL_USERNAME and config.PORTAL_PASSWORD)
    if msg := st.session_state.pop("flash", None):
        st.success(msg)

    a, b = st.columns([1, 1.4])
    with a:
        st.markdown(f"#### Ingest T-1 ({yesterday:%d %b %Y})")
        if not have_creds:
            st.warning("Portal credentials not set. Add PB_PORTAL_USERNAME / PB_PORTAL_PASSWORD to `.env`.")
        demo = st.toggle("Use synthetic demo data (offline test)", value=not have_creds)
        if st.button(f"▶ Ingest {yesterday:%d %b}", type="primary", width="stretch"):
            run_ingest(yesterday, yesterday, demo)
        with st.expander("Backfill a custom range"):
            rng = st.date_input("Range", (yesterday - timedelta(days=6), yesterday), max_value=yesterday)
            force = st.checkbox("Re-classify calls already stored")
            if st.button("Run backfill") and isinstance(rng, tuple) and len(rng) == 2:
                run_ingest(rng[0], rng[1], demo, force)
        st.caption("Automate with cron: `15 7 * * * cd <repo>/pb_health_analytics && python daily_ingest.py`")
    with b:
        st.markdown("#### Ingestion history")
        if runs.empty:
            st.caption("No runs yet.")
        else:
            st.dataframe(runs[["run_id", "mode", "date_from", "date_to", "started_at", "calls_found", "calls_analyzed", "status", "message"]],
                         width="stretch", hide_index=True, height=260)

    st.markdown("---")
    st.markdown("#### Historical progress")
    if df.empty:
        return empty_state()
    tr = metrics.daily_trend(df, denoms)
    if tr.empty:
        return
    window = st.select_slider("Smoothing (rolling days)", [1, 3, 7], value=3)
    sm = tr.set_index("date").rolling(window, min_periods=1).mean().reset_index()
    c1, c2 = st.columns(2)
    with c1:
        fig = px.line(sm, x="date", y=["ppr_pct", "story_adherence", "app_push_pct", "objection_rate_pct"],
                      title="KPIs over time", color_discrete_sequence=[NAVY, TEAL, ORANGE, RED])
        fig.update_layout(height=360, legend_title="", yaxis_title="", xaxis_title="", margin=dict(l=0, r=0, t=40, b=0),
                          legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, width="stretch")
    with c2:
        share_cols = [f"share_{h}" for h in config.HUB_ORDER]
        m = sm.melt(id_vars="date", value_vars=share_cols, var_name="hub", value_name="share")
        m["hub"] = m["hub"].str.replace("share_", "", regex=False)
        fig = px.area(m, x="date", y="share", color="hub", color_discrete_map=HUB_COLORS, title="Location share over time (%)")
        fig.update_layout(height=360, legend_title="", yaxis_title="", xaxis_title="", margin=dict(l=0, r=0, t=40, b=0),
                          legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, width="stretch")
    fig = px.bar(tr, x="date", y=["calls_pitched"], title="Calls pitched per day", color_discrete_sequence=[TEAL])
    fig.add_scatter(x=tr["date"], y=tr["calls_analyzed"], name="calls analysed", line=dict(color=NAVY))
    fig.update_layout(height=300, legend_title="", yaxis_title="", xaxis_title="", margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, width="stretch")
    st.download_button("Download daily KPI CSV", tr.to_csv(index=False), "pb_health_daily_kpis.csv", "text/csv")


def run_ingest(start: date, end: date, demo: bool, force: bool = False):
    bar = st.progress(0.0, text="Starting…")
    try:
        stats = analyzer.ingest_range(start, end, mode="daily", demo=demo, force=force,
                                      progress=lambda p, m: bar.progress(min(max(p, 0.0), 1.0), text=m))
        st.session_state["flash"] = f"Ingested {start} → {end}: {stats['analyzed']} new calls analysed ({stats['found']} found)."
        refresh()
        st.rerun()
    except Exception as exc:
        st.error(f"Ingestion failed: {exc}")


{"1": page_exec, "2": page_drill, "3": page_explorer, "4": page_ingest}[page[0]]()
