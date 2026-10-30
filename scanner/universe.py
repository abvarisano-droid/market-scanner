"""Index definitions and constituent universes (US + global)."""
from __future__ import annotations

import io
import logging

import pandas as pd

log = logging.getLogger(__name__)

# Index level tickers (Yahoo Finance symbols) shown on the dashboard
INDEXES = {
    "S&P 500": "^GSPC",
    "Nasdaq 100": "^NDX",
    "Dow Jones": "^DJI",
    "Russell 2000": "^RUT",
    "FTSE 100 (UK)": "^FTSE",
    "DAX (Germany)": "^GDAXI",
    "CAC 40 (France)": "^FCHI",
    "Euro Stoxx 50": "^STOXX50E",
    "Nikkei 225 (Japan)": "^N225",
    "Hang Seng (HK)": "^HSI",
    "Shanghai Composite": "000001.SS",
    "Sensex (India)": "^BSESN",
    "ASX 200 (Australia)": "^AXJO",
    "TSX (Canada)": "^GSPTSE",
    "Bovespa (Brazil)": "^BVSP",
    "KOSPI (Korea)": "^KS11",
}

BENCHMARK = "SPY"

# Fallback constituents: largest names per index. US lists are pulled live
# from Wikipedia when possible, global lists use these mega-cap baskets.
FALLBACK = {
    "S&P 500": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "AVGO", "TSLA", "JPM",
                "LLY", "V", "UNH", "XOM", "MA", "JNJ", "PG", "HD", "COST", "ABBV", "WMT", "NFLX",
                "BAC", "CRM", "KO", "CVX", "MRK", "AMD", "PEP", "ORCL", "TMO", "ADBE", "LIN", "MCD",
                "CSCO", "ACN", "ABT", "WFC", "DIS", "INTU", "PFE", "CAT", "QCOM", "IBM", "GS"],
    "Nasdaq 100": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "COST", "NFLX",
                   "AMD", "PEP", "ADBE", "CSCO", "TMUS", "INTU", "QCOM", "AMAT", "TXN", "ISRG",
                   "BKNG", "HON", "VRTX", "PANW", "MU", "LRCX", "ADI", "SBUX", "GILD", "MELI"],
    "Dow Jones": ["AAPL", "MSFT", "UNH", "GS", "HD", "CAT", "AMGN", "MCD", "V", "CRM", "TRV", "AXP",
                  "JPM", "IBM", "HON", "AMZN", "PG", "JNJ", "BA", "CVX", "MRK", "WMT", "DIS",
                  "NKE", "KO", "CSCO", "MMM", "VZ", "SHW", "NVDA"],
    "FTSE 100 (UK)": ["AZN.L", "SHEL.L", "HSBA.L", "ULVR.L", "BP.L", "RIO.L", "GSK.L", "REL.L",
                      "DGE.L", "BATS.L", "LSEG.L", "GLEN.L", "BARC.L", "LLOY.L", "RR.L"],
    "DAX (Germany)": ["SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE", "MBG.DE", "BMW.DE",
                      "BAS.DE", "MUV2.DE", "IFX.DE", "DBK.DE", "VOW3.DE", "ADS.DE", "BAYN.DE"],
    "CAC 40 (France)": ["MC.PA", "OR.PA", "RMS.PA", "TTE.PA", "SAN.PA", "AIR.PA", "SU.PA",
                        "BNP.PA", "AI.PA", "EL.PA", "KER.PA", "CS.PA", "DG.PA", "SAF.PA"],
    "Euro Stoxx 50": ["ASML.AS", "INGA.AS", "ADYEN.AS", "ITX.MC", "SAN.MC", "IBE.MC", "ENEL.MI",
                      "ISP.MI", "UCG.MI", "NOKIA.HE"],
    "Nikkei 225 (Japan)": ["7203.T", "6758.T", "9984.T", "8306.T", "6861.T", "9432.T", "8035.T",
                           "6501.T", "7974.T", "4063.T", "9983.T", "6098.T", "8058.T", "7267.T"],
    "Hang Seng (HK)": ["0700.HK", "9988.HK", "0005.HK", "1299.HK", "0941.HK", "3690.HK",
                       "1810.HK", "0388.HK", "2318.HK", "0883.HK", "9618.HK", "1211.HK"],
    "Shanghai Composite": ["600519.SS", "601398.SS", "600036.SS", "601318.SS", "600900.SS",
                           "601288.SS", "600276.SS", "601012.SS"],
    "Sensex (India)": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
                       "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LT.NS"],
    "ASX 200 (Australia)": ["BHP.AX", "CBA.AX", "CSL.AX", "NAB.AX", "WBC.AX", "ANZ.AX",
                            "WES.AX", "MQG.AX", "FMG.AX", "WOW.AX", "TLS.AX", "RIO.AX"],
    "TSX (Canada)": ["RY.TO", "TD.TO", "SHOP.TO", "ENB.TO", "CNQ.TO", "CP.TO", "CNR.TO",
                     "BMO.TO", "BN.TO", "ATD.TO", "SU.TO", "TRI.TO"],
    "Bovespa (Brazil)": ["VALE3.SA", "PETR4.SA", "ITUB4.SA", "BBDC4.SA", "B3SA3.SA",
                         "ABEV3.SA", "WEGE3.SA", "BBAS3.SA"],
    "KOSPI (Korea)": ["005930.KS", "000660.KS", "373220.KS", "207940.KS", "005380.KS",
                      "035420.KS", "051910.KS", "000270.KS"],
}

WIKI = {
    "S&P 500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "Symbol"),
    "Nasdaq 100": ("https://en.wikipedia.org/wiki/Nasdaq-100", "Ticker"),
    "Dow Jones": ("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average", "Symbol"),
}


def _wiki_constituents(name: str) -> list[str]:
    import requests

    url, col = WIKI[name]
    html = requests.get(url, headers={"User-Agent": "market-scanner/1.0"}, timeout=20).text
    for table in pd.read_html(io.StringIO(html)):
        if col in table.columns and len(table) >= 25:
            return [str(t).replace(".", "-").strip() for t in table[col].dropna()]
    raise ValueError(f"no table with column {col}")


def constituents(name: str, live: bool = True) -> list[str]:
    if live and name in WIKI:
        try:
            return _wiki_constituents(name)
        except Exception as exc:  # network or layout change: fall back quietly
            log.warning("live constituents for %s failed (%s), using fallback", name, exc)
    return list(FALLBACK.get(name, []))


def full_universe(indexes: list[str] | None = None, live: bool = True) -> dict[str, str]:
    """Return {ticker: index_name}. First index listed wins for duplicates."""
    out: dict[str, str] = {}
    for name in indexes or list(FALLBACK):
        for t in constituents(name, live=live):
            out.setdefault(t, name)
    return out
