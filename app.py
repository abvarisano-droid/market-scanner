"""Market Scanner dashboard. Run: streamlit run app.py"""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from scanner import data, news_ai, pipeline, signals, universe, valuation
from scanner.labels import COLOR as CALL_COLOR, normalize

st.set_page_config(page_title="Market Scanner", page_icon="📈", layout="wide")
LATEST = Path(__file__).parent / "data" / "latest_scan.json"


@st.cache_data(ttl=600)
def load_scan():
    return json.loads(LATEST.read_text()) if LATEST.exists() else None


def pct(x):
    return "n/a" if x is None or pd.isna(x) else f"{x:+.1%}"


# ---------- sidebar ----------
st.sidebar.title("📈 Market Scanner")
with st.sidebar.expander("Run a new scan", expanded=False):
    picked = st.multiselect("Indexes", list(universe.FALLBACK), default=list(universe.FALLBACK))
    cap = st.number_input("Max stocks (0 = all)", 0, 3000, 0, step=50)
    if st.button("Run scan", type="primary"):
        with st.spinner("Pulling prices, fundamentals and news..."):
            pipeline.run(picked, max_tickers=cap or None)
        st.cache_data.clear()
        st.rerun()

scan = load_scan()
if not scan:
    st.info("No scan yet. Open **Run a new scan** in the sidebar, or run `python run_scan.py`.")
    st.stop()
st.sidebar.caption(f"Last scan: {scan['date']} · {len(scan['table'])} stocks")

tabs = st.tabs(["🌍 Indexes", "🎯 Calls", "💸 Mispricing", "⚡ Movers & Sectors", "🏆 Track Record", "🔎 Deep Dive"])

# ---------- indexes ----------
with tabs[0]:
    idx = pd.DataFrame(scan["indexes"])
    cols = st.columns(4)
    for i, r in idx.iterrows():
        cols[i % 4].metric(r["name"], f"{r['level']:,.0f}", pct(r["chg_1d"]))
    fig = px.bar(idx.sort_values("chg_1m"), x="chg_1m", y="name", orientation="h",
                 color="chg_1m", color_continuous_scale="RdYlGn", labels={"chg_1m": "1M return", "name": ""})
    fig.update_layout(xaxis_tickformat=".0%", coloraxis_showscale=False, height=500)
    st.plotly_chart(fig, width="stretch")

# ---------- calls ----------
with tabs[1]:
    picks = pd.DataFrame(scan["picks"])
    picks["call"] = picks["call"].map(normalize)
    f = st.radio("Show", ["All", "Bullish", "Bearish", "Neutral"], horizontal=True)
    if f != "All":
        picks = picks[picks["call"] == f]
    for _, p in picks.sort_values("mispricing", ascending=False).iterrows():
        with st.container(border=True):
            a, b, c, d = st.columns([3, 1, 1, 1])
            a.markdown(f"### {p['ticker']} · {p.get('shortName') or ''}\n{p.get('index')} · {p.get('sector') or ''}")
            b.markdown(f"<h3 style='color:{CALL_COLOR[p['call']]}'>{p['call']}</h3>", unsafe_allow_html=True)
            c.metric("Mispricing", f"{p['mispricing']:+.0f}")
            d.metric("Confidence", p.get("confidence"))
            st.write(p.get("thesis", ""))
            if p.get("catalysts"):
                st.caption(f"**Catalysts:** {p['catalysts']} · **Risks:** {p.get('risks', '')}")
            for h in (p.get("headlines") or [])[:4]:
                st.markdown(f"- [{h['title']}]({h['link']}) <span style='color:gray'>{h.get('publisher', '')}</span>",
                            unsafe_allow_html=True)

# ---------- mispricing screener ----------
with tabs[2]:
    t = pd.DataFrame(scan["table"])
    c1, c2, c3 = st.columns(3)
    idx_f = c1.multiselect("Index", sorted(t["index"].dropna().unique()))
    sec_f = c2.multiselect("Sector", sorted(t["sector"].dropna().unique()))
    rng = c3.slider("Mispricing score", -100, 100, (-100, 100))
    v = t[t["mispricing"].between(*rng)]
    if idx_f:
        v = v[v["index"].isin(idx_f)]
    if sec_f:
        v = v[v["sector"].isin(sec_f)]
    fig = px.scatter(v, x="value_z", y="quality_z", color="mispricing", hover_name="ticker",
                     hover_data=["shortName", "forwardPE", "analyst_upside"], color_continuous_scale="RdYlGn",
                     labels={"value_z": "Cheapness vs peers →", "quality_z": "Quality vs peers →"})
    fig.add_hline(y=0, line_dash="dot"); fig.add_vline(x=0, line_dash="dot")
    st.plotly_chart(fig, width="stretch")
    st.caption("Top right = cheap AND high quality, the sweet spot.")
    show = ["ticker", "shortName", "index", "sector", "price", "mispricing", "forwardPE", "enterpriseToEbitda",
            "fcf_yield", "analyst_upside", "chg_3m", "rsi"]
    st.dataframe(v.sort_values("mispricing", ascending=False)[show], width="stretch", hide_index=True,
                 column_config={k: st.column_config.NumberColumn(format="percent")
                                for k in ["fcf_yield", "analyst_upside", "chg_3m"]})

# ---------- movers & sectors ----------
with tabs[3]:
    a, b = st.columns([3, 2])
    with a:
        st.subheader("Unusual activity")
        mv = pd.DataFrame(scan["movers"])
        if not mv.empty:
            mv["flags"] = mv["flags"].map(", ".join)
            st.dataframe(mv, width="stretch", hide_index=True,
                         column_config={"chg_1d": st.column_config.NumberColumn(format="percent")})
    with b:
        st.subheader("Sector rotation")
        sec = pd.DataFrame(scan["sectors"])
        if not sec.empty:
            fig = px.bar(sec, x="acceleration", y="sector", orientation="h", color="acceleration",
                         color_continuous_scale="RdYlGn")
            fig.update_layout(xaxis_tickformat=".1%", coloraxis_showscale=False)
            st.plotly_chart(fig, width="stretch")
            st.caption("Positive = sector gaining leadership this month vs its 3-month pace.")

# ---------- track record ----------
with tabs[4]:
    sc = scan["scorecard"]
    m = st.columns(5)
    m[0].metric("Total calls", sc.get("total_picks", 0))
    m[1].metric("Open win rate", pct(sc.get("open_win_rate")).lstrip("+"))
    m[2].metric("Avg alpha (open)", pct(sc.get("open_avg_alpha")))
    m[3].metric("20D hit rate", pct(sc.get("hit_rate_20d")).lstrip("+"), help=f"n={sc.get('n_20d', 0)}")
    m[4].metric("60D hit rate", pct(sc.get("hit_rate_60d")).lstrip("+"), help=f"n={sc.get('n_60d', 0)}")
    st.caption("A call is 'right' if it beat SPY in its direction: Bullish calls outperform, Bearish calls lag. Entry is the next trading day's close. Under 21 trading days of history the record is still noise. Not investment advice.")
    st.info(f"{sc.get('status', 'still noise')}: {sc.get('note', '')}")
    led = pd.DataFrame(scan["ledger"])
    if not led.empty:
        led["call"] = led["call"].map(normalize)
        led["verdict"] = led["alpha_now"].map(lambda a: "✅ right" if a and a > 0 else ("❌ wrong" if a is not None else "⏳"))
        cols = [c for c in ["date", "ticker", "call", "confidence", "entry", "ret_now", "alpha_now", "verdict",
                            "alpha_20d", "alpha_60d", "thesis"] if c in led]
        st.dataframe(led[cols].sort_values("date", ascending=False), width="stretch", hide_index=True,
                     column_config={k: st.column_config.NumberColumn(format="percent")
                                    for k in ["ret_now", "alpha_now", "alpha_20d", "alpha_60d"]})

# ---------- deep dive ----------
with tabs[5]:
    tk = st.text_input("Any ticker (e.g. NVDA, ASML.AS, 7203.T)").strip().upper()
    if tk:
        with st.spinner(f"Analyzing {tk}..."):
            px_map = data.prices([tk], period="2y")
            if tk not in px_map:
                st.error("No price data for that ticker.")
                st.stop()
            df = px_map[tk]
            known = pd.DataFrame(scan["table"]).set_index("ticker")
            tech = signals.technicals(df)
            row_t = pd.DataFrame([{**tech, "index": None}], index=[tk]).join(data.fundamentals([tk]))
            # score against the scanned universe so peers are real
            pool = pd.concat([known.drop(index=tk, errors="ignore"), row_t])
            row = valuation.score(pool).loc[tk].to_dict() | {"ticker": tk}
            res = news_ai.analyze(row, data.news(tk))
        a, b, c, d = st.columns(4)
        a.markdown(f"<h2 style='color:{CALL_COLOR[normalize(res['call'])]}'>{normalize(res['call'])}</h2>", unsafe_allow_html=True)
        b.metric("Mispricing", f"{row['mispricing']:+.0f}")
        c.metric("News sentiment", f"{res['sentiment']:+.2f}")
        d.metric("Analyst upside", pct(row.get("analyst_upside")))
        st.write(res["thesis"])
        for r in row.get("valuation_reasons") or []:
            st.markdown(f"- {r}")
        fig = go.Figure(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"]))
        fig.add_scatter(x=df.index, y=df["Close"].rolling(50).mean(), name="50D")
        fig.add_scatter(x=df.index, y=df["Close"].rolling(200).mean(), name="200D")
        fig.update_layout(xaxis_rangeslider_visible=False, height=450)
        st.plotly_chart(fig, width="stretch")
        for h in res["headlines"]:
            st.markdown(f"- [{h['title']}]({h['link']})")
