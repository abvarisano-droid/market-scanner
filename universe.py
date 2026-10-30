"""S&P 500 universe from Wikipedia, cached to data/universe.csv."""
import argparse, html, re, urllib.request
from pathlib import Path
import pandas as pd

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def parse_universe(page: str) -> pd.DataFrame:
    """Parse the constituents table out of the Wikipedia HTML. Tickers use Yahoo style (BRK-B)."""
    m = re.search(r'<table[^>]*id="constituents".*?</table>', page, re.S)
    if not m:
        raise ValueError("constituents table not found")
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", m.group(0), re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) >= 3 and cells[0]:
            rows.append({"ticker": cells[0].replace(".", "-"), "name": cells[1], "sector": cells[2]})
    df = pd.DataFrame(rows).drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)
    if df.empty:
        raise ValueError("no rows parsed")
    return df


def fetch_universe() -> pd.DataFrame:
    req = urllib.request.Request(URL, headers={"User-Agent": "market-scanner/1.0 (research tool)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return parse_universe(r.read().decode("utf-8"))


def load_universe(path="data/universe.csv", refresh=False) -> pd.DataFrame:
    p = Path(path)
    if p.exists() and not refresh:
        return pd.read_csv(p)
    df = fetch_universe()
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="data/universe.csv")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    print(len(load_universe(a.path, a.refresh)), "tickers")
