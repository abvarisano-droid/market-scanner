import numpy as np
import pandas as pd

from scanner import valuation


def table(**over):
    n = 6
    base = {"price": [100.0] * n, "targetMeanPrice": [110.0] * n, "numberOfAnalystOpinions": [20] * n,
            "freeCashflow": [1e9] * n, "marketCap": [2e10] * n, "chg_3m": [0.0] * n, "volatility": [0.3] * n,
            "sector": ["Tech"] * n, "forwardPE": [15.0, 16, 17, 18, 19, 20], "trailingPE": [18.0, 19, 20, 21, 22, 23],
            "enterpriseToEbitda": [10.0] * n, "priceToBook": [3.0] * n, "returnOnEquity": [0.1] * n,
            "profitMargins": [0.1] * n, "revenueGrowth": [0.05] * n, "debtToEquity": [50.0] * n}
    base.update(over)
    return pd.DataFrame(base, index=list("ABCDEF"))


def test_absurd_analyst_gap_is_dropped_with_its_reason():
    t = table(targetMeanPrice=[190.0, 30.0, 110.0, 179.0, 41.0, 110.0])  # +90%, -70%, ok, +79%, -59%, ok
    out = valuation.score(t.assign(chg_3m=0.0))
    assert out["analyst_upside"].isna().tolist() == [True, True, False, False, False, False]
    assert not any("Analyst consensus" in r for i in "AB" for r in out.loc[i, "valuation_reasons"])
    assert out.loc[["A", "B"], "analyst_z"].fillna(0).eq(0).all()


def test_tiny_forward_pe_without_trailing_is_dropped():
    t = table(forwardPE=[2.5, 2.5, 15, 16, 17, 18], trailingPE=[np.nan, 9.0, 18, 19, 20, 21])
    out = valuation.score(t)
    assert np.isnan(out.loc["A", "forwardPE"])  # no trailing P/E: artifact
    assert out.loc["B", "forwardPE"] == 2.5  # trailing P/E present: kept
