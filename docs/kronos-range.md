# Kronos model range on stock pages

Status: built on branch `claude/kronos-fan` (2026-11-02), PR only; Ashton merges. Asked for by Ashton on 2026-11-02 ("Yes please" to the Kronos plan): a Kronos range fan on stock pages next to the existing replay fan, showing how often its p10 to p90 range actually held over the last 20 trading days. The look is Grok's (design owner since 2026-11-01); this pass reuses the replay's tokens and panel cells and leaves the visual pass to Grok.

A model range, not a prediction. Not investment advice.

## 1. What it is

Each night after the scan, the open-source Kronos-small model (MIT, pinned in `kronos/MANIFEST.json`) reads the last 64 daily candles of a stock page and samples 100 price paths over the next 20 trading days (the replay's window). The page shows:

- a static fan: the last 30 closes, the 10th to 90th percentile band, the middle (50th percentile) path and 16 of the sampled paths;
- the share of paths ending above versus below the last close (the replay's 20 segment bar);
- "Kronos held its p10 to p90 range on X of the last 20 days", or, while fewer than 20 days are scored, "on X of N scored days so far (fewer than 20)".

## 2. Honest framing

- Label everywhere: "A model range, not a prediction. Not investment advice."
- No look-ahead: the input is the chart file the scan just wrote, which ends at the scan's last completed close; `model_input` refuses a file whose last candle is not its as-of date.
- Walk-forward count: each night's next-day 10th to 90th band (as returns) is appended to `data/kronos_log.csv` before the next session exists. A band is scored against the first daily candle after its base date. Nothing is backfilled, so the count starts at zero and builds one day at a time; the page says so until 20 days are scored.
- Baseline on the tile: "A well calibrated 10th to 90th band holds about 8 in 10 days."
- Observation on the 2026-10-30 data (unverified beyond three tickers): Kronos-small with 64 candles leans hard toward mean reversion after a run up (ABBV: all 100 paths end lower, middle path minus 9.7% over 20 days). The held count is how a visitor sees whether that is calibrated.

## 3. Data

| Item | Definition |
|---|---|
| Model | NeoQuasar/Kronos-small at revision 901c26c1332695a2a8f243eb2f37243a37bea320, tokenizer NeoQuasar/Kronos-Tokenizer-base at 0e0117387f39004a9016484a186a908917e22426; code from shiyu-coder/Kronos at 67b630e67f6a18c9e9be918d9b4337c960db1e9a |
| Loading | safetensors only, sha256 checked against the manifest; pickle weight files are refused; config keys and types are checked |
| Sampling | T 1.0, top_p 0.9 (the upstream README defaults), 100 paths, seed from the ticker and date |
| Input | last 64 daily candles (open, high, low, close, volume) from `data/charts.json`, split and dividend adjusted |
| Output file | `site/data/kronos/<T>.json`: as-of, base close, dates, p10, p50 and p90 per step, up and down counts, 16 paths, last 30 closes, held count and text; `index.json` lists the pages that have one |
| Tickers | stock-page tickers (the scan's called names). `data/kronos_watchlist.json` (empty: the Market Team watchlist is private) goes first, then the pages whose range is missing or oldest; at most 36 a night |
| Runtime | about 20 to 35 s per ticker measured on a 4 core CPU (shared sandbox; up to 100 s under heavy load); the model step stops starting tickers after 13 minutes |

## 4. Spec (WEB_DESIGN_REFERENCE section 6, short form)

```
ONE SIGNATURE MOMENT: none; a static card under the 3-year chart, the replay stays the animated piece
TYPE: the replay panel's mono 10 / 11 / 13 px and 24 px numbers; h2 in the site serif
PALETTE: the replay tokens (--rg-*): teal band and up paths, orange down paths, median #d9f9f7, stage --kx-stage
MOTION: none (static SVG), so reduced motion needs no fallback; the card is its own static fallback
LAYOUT: stage 220 px high from the first paint, then the replay's panel cells (3 columns, 2 on phones)
PERF: one small JSON per page (about 4 KB) behind a shared index; no request for a page without a range
```

Layout alternatives considered (no screenshots compared; Grok owns the visual pass):
- A, card under the chart (built): nothing on the chart moves, works the same on phones.
- B, a "Kronos" pill in the layer row that overlays the fan on the plot like the replay: more striking, but stacks two overlays on one plot.
- C, replay and Kronos side by side on desktop: best comparison, but squeezes both under 900 px.

## 5. Checked on this branch

- `python -m pytest -q`: 185 tests pass, including `tests/test_kronos.py` (band math, walk-forward count capped at 20, no look-ahead, append-only log, output checks, tampered input, pins, honest copy).
- Headless Chromium at 390 x 844 and 1280 x 900 on ABBV (with a trial range) and ALB (without): no console errors, no horizontal overflow.
- Not run here: Lighthouse, and a real GitHub Actions run (no dispatch from this session).
