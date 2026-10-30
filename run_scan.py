"""CLI: python run_scan.py [--indexes "S&P 500" "DAX (Germany)"] [--max 200]"""
import argparse
import logging

from scanner import pipeline

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--indexes", nargs="*")
    ap.add_argument("--max", type=int)
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    res = pipeline.run(a.indexes, top_n=a.top, max_tickers=a.max)
    print(f"Scanned {len(res['table'])} stocks, {len(res['picks'])} calls. Report: reports/{res['date']}.md")
