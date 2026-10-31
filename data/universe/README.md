# Universe lists

`russell2000.csv`: Russell 2000 constituents (US equities only) from the iShares Russell 2000 ETF (IWM) holdings file, as of 2026-10-29. Downloaded by hand from ishares.com on 2026-10-31, because the automated holdings link returns a web page instead of the CSV. Parsed with `scanner.universe.parse_ishares_holdings`, 1,922 tickers. The scan uses a fresh pull when one works and falls back to this file otherwise. Refresh it after the Russell reconstitution each June.
