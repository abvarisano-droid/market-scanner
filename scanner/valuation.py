"""Mispricing model: relative value vs sector peers, quality, analyst gap, momentum.

Each stock gets a composite score from -100 (looks overpriced) to +100 (looks
underpriced). Every component also produces a plain-English reason so the
"why" is always visible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# (column, direction): +1 means higher is cheaper/better, -1 means lower is cheaper
VALUE_METRICS = [("forwardPE", -1), ("trailingPE", -1), ("enterpriseToEbitda", -1),
                 ("priceToBook", -1), ("fcf_yield", +1)]
QUALITY_METRICS = [("returnOnEquity", +1), ("profitMargins", +1), ("revenueGrowth", +1),
                   ("debtToEquity", -1)]

UPSIDE_MAX, UPSIDE_MIN, MIN_FWD_PE = 0.8, -0.6, 4
WEIGHTS = {"value": 0.40, "quality": 0.20, "analyst": 0.25, "momentum": 0.15}


def _peer_z(df: pd.DataFrame, col: str, direction: int) -> pd.Series:
    s = pd.to_numeric(df[col], errors="coerce")
    if col in ("forwardPE", "trailingPE", "enterpriseToEbitda", "priceToBook"):
        s = s.where(s > 0)  # negative multiples are meaningless for cheapness
    grp = df["sector"].fillna("Unknown")

    def z(x: pd.Series) -> pd.Series:
        x = x.clip(x.quantile(0.05), x.quantile(0.95))
        sd = x.std()
        if x.count() < 3 or not sd:
            # too few sector peers: fall back to market-wide
            return pd.Series(np.nan, index=x.index)
        return (x - x.median()) / sd

    out = s.groupby(grp).transform(z)
    market = (s - s.median()) / (s.std() or 1)
    return direction * out.fillna(market).clip(-3, 3)


def score(table: pd.DataFrame) -> pd.DataFrame:
    df = table.copy()
    df["fcf_yield"] = pd.to_numeric(df["freeCashflow"], errors="coerce") / pd.to_numeric(df["marketCap"], errors="coerce")
    df["analyst_upside"] = pd.to_numeric(df["targetMeanPrice"], errors="coerce") / df["price"] - 1
    # a consensus gap above +80% or below -60% is almost always a currency or unit mismatch: treat as missing
    df["analyst_upside"] = df["analyst_upside"].where((df["analyst_upside"] <= UPSIDE_MAX) & (df["analyst_upside"] >= UPSIDE_MIN))
    # a forward P/E under 4 with no trailing P/E is a unit or currency artifact (seen on KRW names): drop it
    fpe = pd.to_numeric(df["forwardPE"], errors="coerce")
    df["forwardPE"] = fpe.where(~((fpe < MIN_FWD_PE) & pd.to_numeric(df["trailingPE"], errors="coerce").isna()))

    def block(metrics):
        z = pd.concat([_peer_z(df, c, d).rename(c) for c, d in metrics], axis=1)
        return z, z.mean(axis=1)

    vz, df["value_z"] = block(VALUE_METRICS)
    qz, df["quality_z"] = block(QUALITY_METRICS)
    n_analysts = pd.to_numeric(df["numberOfAnalystOpinions"], errors="coerce").fillna(0)
    conf = (n_analysts / 10).clip(0, 1)
    df["analyst_z"] = (df["analyst_upside"].clip(-0.5, 0.8) / 0.15 * conf).clip(-3, 3)
    # mean reversion lens: deep 3m drawdown in a quality name = opportunity; huge run-up = stretched
    df["momentum_z"] = (-(df["chg_3m"] / (df["volatility"].replace(0, np.nan) / 2))).clip(-3, 3)

    comp = sum(df[f"{k}_z"].fillna(0) * w for k, w in WEIGHTS.items())
    df["mispricing"] = (comp / 2 * 100).clip(-100, 100).round(0)
    df["coverage"] = pd.concat([vz, qz], axis=1).notna().mean(axis=1)

    df["valuation_reasons"] = [_reasons(r, vz.loc[i], qz.loc[i]) for i, r in df.iterrows()]
    return df


def _reasons(r: pd.Series, vz: pd.Series, qz: pd.Series) -> list[str]:
    out = []
    labels = {"forwardPE": "forward P/E", "trailingPE": "trailing P/E", "enterpriseToEbitda": "EV/EBITDA",
              "priceToBook": "P/B", "fcf_yield": "FCF yield"}
    for col, z in vz.dropna().items():
        if abs(z) >= 1:
            val = r.get(col)
            shown = f"{val:.1%}" if col == "fcf_yield" else f"{val:.1f}x"
            out.append(f"{labels[col]} {shown} is {'cheap' if z > 0 else 'rich'} vs {r.get('sector') or 'market'} peers")
    if qz.dropna().mean() >= 0.75:
        out.append("Above-peer quality (ROE, margins, growth)")
    elif qz.dropna().mean() <= -0.75:
        out.append("Below-peer quality, could be a value trap")
    up = r.get("analyst_upside")
    if pd.notna(up) and abs(up) >= 0.15 and (r.get("numberOfAnalystOpinions") or 0) >= 5:
        out.append(f"Analyst consensus sits {up:+.0%} from the last close ({int(r['numberOfAnalystOpinions'])} analysts)")
    if pd.notna(r.get("chg_3m")) and abs(r["chg_3m"]) >= 0.2:
        out.append(f"{'Down' if r['chg_3m'] < 0 else 'Up'} {abs(r['chg_3m']):.0%} in 3 months")
    return out
