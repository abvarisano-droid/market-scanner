---
title: Forecast Lab
status: phase 1 on branch claude/project-thread-yrciat
updated: 2026-11-19
---

# Forecast Lab

A model range, not a prediction. Not investment advice. Paper money only: the lab never places
orders, signs in to a brokerage or moves money.

## What it is

A small contest inside market-scanner. Pick a stock and see each model's 5-day price range side by
side, plus a scorecard that says which model has actually been right. Every week each contestant runs
the same 20 paper trades on a simulated local ledger, and a Friday scorecard grades them.

## Contestants

| Model | Weights | License | Notes |
|---|---|---|---|
| Kronos-small | NeoQuasar/Kronos-small (pinned, sha256 in `kronos/MANIFEST.json`) | MIT | 24.7M params, 512 context. Our current next-day 80% bands held 46% (58 of 127). |
| TimesFM 2.5 | google/timesfm-2.5-200m-pytorch | Apache-2.0 | Install: clone the TimesFM repo, `pip install -e .[torch]`. |
| Chronos-Bolt small | amazon/chronos-bolt-small | Apache-2.0 | `pip install chronos-forecasting`. |
| Moirai 2 small | Salesforce/moirai-2.0-R-small | CC-BY-NC-4.0 | Non-commercial weights, fine for personal use. `pip install uni2ts`. Adapter unverified. |
| Options-implied move | Yahoo option chains via yfinance | n/a | Live only (no free option history, so no backtest). Cboe's delayed-quotes JSON is not used: its terms forbid automated downloads. |
| Random walk, GBM, bootstrap | none | n/a | Baselines. A model has to beat the random walk to count. |

Every contestant returns the same thing: 5 trading days of log-return quantiles at 10%, 20%, ... 90%.
Each also gets a calibrated twin (`+cal`) that stretches its range using only past, already-scored
forecasts, so the 80% range really holds about 80% of the time.

## Scores

- **Range held:** share of outcomes inside the 10 to 90% range (aim 80%), with a 95% Wilson range.
- **Brier on P(up):** lower is better; a coin flip scores 0.25.
- **CRPS:** overall accuracy of the whole range (2 x mean pinball loss); lower is better.
- **Skill vs random walk:** 1 minus CRPS ratio, paired on the same ticker and date. Above 0 beats it.
- **Direction hit rate:** how often the median called the right direction.

## Phase 1 (built): contest harness and scoring

Package `forecast_lab/`:

- `core.py`: the `Forecast` shape, quantile CDF, price helpers.
- `baselines.py`: random walk, GBM, block bootstrap (seeded).
- `models.py`: Kronos-small, TimesFM 2.5, Chronos-Bolt small, Moirai 2 small adapters. Each fails
  soft (`ContestantUnavailable`) when its package or weights are missing. Only the Kronos path has
  run before; the other three adapters follow their docs and have never been run.
- `options_move.py`: options-implied move from the at-the-money straddle.
- `calibrate.py`: the no-look-ahead stretch factor.
- `scoring.py`: pinball, CRPS, Brier, PIT, Wilson, paired skill, summary.
- `walkforward.py`: walk-forward backtest. Each model sees only history up to the forecast date.
- `report.py`: writes `contest-YYYY-MM-DD.md` and `.json`.

Tests: `python -m pytest tests/test_forecast_lab.py` (17 tests, including a check that no model ever
sees the future).

### Run it

```
pip install -r requirements.txt yfinance
python -m forecast_lab weights
python -m forecast_lab backtest --weeks 52
```

Add the other contestants as you install them:

```
pip install chronos-forecasting uni2ts
python -m forecast_lab backtest --models random_walk,gbm,bootstrap,kronos_small,chronos_bolt_small,moirai_2_small,timesfm_2_5 --weeks 52
```

Your own holdings and watchlist stay off this public repo: put them one ticker per line in a local
file outside the repo and pass `--extra-file <path>`. Prices cache in `data/cache/forecast_lab/` and
reports land in `reports/forecast_lab/`.

### Done when (phase 1)

- The backtest runs on the Surface for the 30 default tickers over 52 weeks without errors.
- Each installed contestant appears in the report with range held, Brier, CRPS and skill.
- Any contestant that can't run is listed under "skipped" with the reason, not crashed.

## On Windows: setup and the nightly job

From the repo folder in PowerShell:

```
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\forecast_lab_setup.ps1
```

It switches to the branch, makes `.venv`, installs torch (CPU) and the lab's packages, fetches the
Kronos weights, runs the tests, runs a quick 8-week contest and prints the scorecard, then adds a
Task Scheduler job `ForecastLabNightly` (01:30 by default, `-Time "02:00"` to change).

Each night `scripts/forecast_lab_nightly.ps1` runs the tests and the full 52-week contest in plain
Python, then runs Claude Code headless (`claude -p`, Sonnet, 40 turns max) with
`scripts/forecast_lab_night_prompt.txt` to fix any contestant that failed. Claude can edit and commit but
not push; the script pushes only to this branch, and only if every changed file is under
`forecast_lab/`, `tests/` or `docs/`. Logs: `logs/forecast_lab/` (not in git).

The PC must stay on, plugged in and signed in (locked is fine). Pause or remove the job:

```
Disable-ScheduledTask -TaskName ForecastLabNightly
Unregister-ScheduledTask -TaskName ForecastLabNightly -Confirm:$false
```

## Phase 2: paper desks and the Friday scorecard

- One simulated desk per contestant, all running the same rule: each Monday, from the ~100 largest
  US stocks plus the private holdings file, take the 20 names where that model's calibrated P(up) is
  furthest from 50%; long if above, short if below; equal weight; close at Friday's close.
- Ledger is a local JSON file. No broker, no orders.
- Friday scorecard: per desk P&L, hit rate, range held, skill vs random walk, written to
  `reports/forecast_lab/`.
- Runs nightly on the Surface (Task Scheduler or WezTerm), not GitHub Actions.

## Phase 3: one clean screen

Function first, animation last. One page, three parts and nothing else:

1. A stock picker.
2. A chart: the last 60 closes, then each model's 10 to 90% range for the next 5 days as a band.
   Toggle models on and off. Best-scoring model on top.
3. The scorecard table: model, range held, skill, desk P&L this week.

Spec (WEB_DESIGN_REFERENCE section 6):

- SITE: Forecast Lab, one page.
- ONE SIGNATURE MOMENT: the ranges fanning out from today's close (added last, after the page works).
- TYPE: one family, 3 sizes (14, 16, 24), tabular numbers in tables.
- PALETTE: neutral background and text; one color per model, validated for both themes.
- SPACING: 8px scale.
- MOTION: transform and opacity only, one easing curve, reduced-motion shows the final state.
- PERF: Lighthouse 95+, CLS 0.00, LCP under 2s on a phone.
- Footer on every view: "A model range, not a prediction. Not investment advice."

Before markup: 3 layout alternatives compared, then the section 7 anti-slop checklist.

## Build prompt (for Claude Code on the Surface)

```
Read docs/forecast-lab.md in market-scanner. Phase 1 is on branch claude/project-thread-yrciat.
1. git fetch && git checkout claude/project-thread-yrciat
2. pip install -r requirements.txt yfinance chronos-forecasting uni2ts, and TimesFM from its repo.
3. Run python -m pytest tests/test_forecast_lab.py; all must pass.
4. Run python -m forecast_lab weights, then the backtest with every contestant over 52 weeks.
5. If an adapter fails, fix only that adapter against its package's current docs and add a test.
6. Commit only forecast_lab/, tests/ and docs/ files on the same branch, push, and report the
   contest table. Do not merge to main, do not open a PR unless Ashton asks.
Never trade, sign in to a brokerage or move money. Keep personal holdings out of the repo.
```
