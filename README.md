# same-day-trading-lab

A deterministic, historical-replay **fill-honesty lab** for intraday equity research.

The question it exists to answer:

> Can we replay a same-day equity strategy on historical 1-minute bars **without
> lookahead**, and measure how much apparent P&L dies moving from fantasy fills to
> pessimistic fills — and refuse to be fooled by the ones that look good?

## What it is / is not

It **is** a truth engine. It replays one symbol's historical session(s) bar-by-bar behind
a structural no-lookahead firewall, prices each trade two ways (a fantasy "naive" fill and
a serious "pessimistic" fill), sweeps friction to find where the edge dies, and emits a
verdict that **cannot PASS on fantasy fills alone**. It evaluates a small, **pre-registered**
set of strategies and corroborates anything promising on a **holdout** window.

It is **not** a trading bot, broker-execution system, **strategy optimizer**, portfolio
backtester, dashboard, or AI trader. There is no live-order code, no async/threading, no
websockets, no UI, no dynamic/top-volume symbol universe, and no LLM in the decision path.
It never *searches* for an edge — searching across possibilities until something "works" is
the self-deception this lab is built to resist.

## Why it exists (the retired predecessors)

Two predecessors were retired. **Glint** (a Kalshi paper bot) taught that the value was
*discipline* — deterministic math, full observability, raw archival, and treating negative
results as deliverables. **Bob** (an Alpaca equity paper bot) produced paper P&L that is
**not trusted**: paper fills are not truth. This lab copies neither's execution loop and
treats no modeled fill as achievable. A future bot may only ever execute what the lab
approves — and so far it approves nothing; it measures friction honestly.

## Why 1-minute bars deceive

A 1-minute OHLCV bar does **not** reveal what was tradeable inside the minute: not whether
the high preceded the low, whether a breakout preceded its stop, what size traded where,
what the spread was, or whether a real order would have filled. The strategies here are
**pre-registered hypotheses**, not beliefs. The real deliverable is honest fill modeling.

Accordingly, **every report opens with a verbatim `DATA WARNING`**: the free Alpaca/IEX feed
is a *subset* of US volume, bar highs/lows may exclude other venues, there is no quote/spread
data, and **spreads and fills are modeled, not observed**. No P&L here is achievable.

## Install & quickstart

Requires Python 3.11+. Stdlib-minimal; the only runtime deps are `pyyaml` and `tzdata`.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
python -m pytest                      # offline — the suite never touches the network

# end-to-end on the bundled fixture (no credentials needed):
same-day-lab init-db
same-day-lab ingest --provider fixture --symbol AAPL --date 2025-05-15
same-day-lab run    --symbol AAPL --date 2025-05-15      # writes a JSON + Markdown report, prints a verdict
```

Fixtures in `fixtures/` are the default provider, so everything runs offline. See
[Working with real data](#working-with-real-data-alpaca) to pull live IEX sessions.

## Commands

```bash
same-day-lab init-db                                                       # create the SQLite schema
same-day-lab ingest     --provider {fixture|alpaca} --symbol AAPL --date 2025-05-15
same-day-lab run        --symbol AAPL --date 2025-05-15 [--strategy NAME]   # one day: replay + fills + report
same-day-lab run-range  --symbol AAPL --start 2025-06-02 --end 2025-06-13 [--strategy NAME]   # per-day-independent aggregate
same-day-lab tournament --symbol AAPL --decide-start 2025-06-02 --decide-end 2025-06-13 \
                        --holdout-start 2025-06-17 --holdout-end 2025-06-27 # all strategies, decide vs holdout
same-day-lab reconstruct --symbol AAPL --date 2025-05-15 --time "10:32"     # state at an instant; --time is market tz
same-day-lab report     --symbol AAPL --date 2025-05-15                     # locate the latest report
```

`reconstruct --time` is a wall-clock time in the **market timezone** (`America/New_York`),
converted to UTC for lookup; it shows what the system knew at that instant (completed-bar
count, last bar, quality summary) and re-verifies the archived raw payload's hash.

## How it works

`ingest` (archive raw + content hash) → normalize → SQLite → quality checks → no-lookahead
replay → strategy (emits a `TradePlan`) → dual fills → friction sweep → deterministic
JSON+Markdown report → verdict.

- **No-lookahead firewall (structural, not disciplinary).** `ReplayClock` owns all bars
  privately and advances one at a time; a strategy only ever receives a `ReplayView` of
  *completed* bars, with no method that returns a future bar. A signal on bar N fills no
  earlier than bar N+1 — `signal_bar_ts == fill_bar_ts` raises and invalidates the run.
- **Pessimistic fills (the serious path).** Enter on the next bar at
  `max(next_open, trigger) + adverse slippage`; the stop wins ambiguous bars; targets must
  be *exceeded*, not merely touched; a gapped stop fills worse than the stop level; otherwise
  flatten at the flatten time.
- **Naive fills (a labeled lie).** The **same** path re-priced at zero slippage — entry at
  the trigger close, exits at exact levels. By construction `naive_pnl ≥ pessimistic_pnl`.
- **Friction sweep.** Re-runs the pessimistic simulation across a cents × bps grid and reports
  the **crossover** — the friction level at which pessimistic P&L turns non-positive.

## Strategies

Strategies are **pre-registered hypotheses with fixed rules — never tuned or optimized.**
Each emits a generic `TradePlan` (entry trigger + stop + target-R) that the shared fill
engine prices; choose one with `--strategy` (default `orb_long_5m`). All are **long-only**:

| name | hypothesis | stop |
|---|---|---|
| `orb_long_5m` | close above the 5-minute opening-range high (breakout) | OR low |
| `vwap_reclaim_long` | close back above the cumulative session VWAP from below (reclaim) | lowest low since open |
| `or_fade_long` | a failed breakdown below the OR low that closes back above it (bear-trap) | breakdown swing low |

VWAP and all levels are computed from *completed bars only* — the firewall applies to every
strategy. Adding a strategy is a small registry entry; there is **no multi-strategy engine**
(each runs independently, one trade per day, per-share).

## Data quality

Real IEX sessions legitimately omit no-trade minutes, so missing bars are handled by a
tolerance policy (`config/default.yaml` → `quality.missing_bar_policy`):

- **Missing RTH minutes** are non-fatal up to `max_missing_fatal` (default 30); beyond that
  the run is `INVALID_DATA`. The count and timestamps are surfaced in every report.
- **`halt_suspected`** — an *interior* consecutive-missing run ≥ `halt_run_min_consecutive`
  (default 10) — is flagged but **non-fatal**.
- **`partial_session`** — a leading/trailing missing run that reaches a session edge — means
  the feed never covered the full session, and is **fatal**.
- Suspicious OHLC and duplicate bars are always fatal. **Bars are never fabricated** to fill
  gaps. (Split/adjustment detection is deferred — it needs multi-day context.)

## Multi-day (`run-range`)

Replays the same symbol + strategy across a date range, **each day fully independent** (its
own opening range, one trade, no carry-over, no compounding, per-share P&L). The aggregate
(`reports/<symbol>_<start>_<end>_aggregate.{json,md}`) is a **descriptive distribution, not a
track record**: a per-day table, counts (traded / no-signal / `INVALID_DATA`, naive>0,
survived-friction, KILL), a crossover-cents distribution, and the **fill-honesty headline**
(how many days naive looked profitable but pessimistic killed). There is **no aggregate
verdict** and **no portfolio math** (no equity curve, drawdown, or Sharpe). Range dates with
no ingest are surfaced as *missing* (record them, or they were holidays — there is no market
calendar). `aggregate_hash` makes it deterministic. It runs only over already-ingested days.

## Tournament (the anti-overfitting layer)

Evaluates the **whole pre-registered strategy set** over a **decide** window and an unseen
**holdout** window, producing a descriptive leaderboard. A strategy is `carried_forward` only
if it **survives both windows**, where *survives* = ≥3 traded days, a **strict >50% majority**
of traded days clear the friction threshold, and zero fill-honesty KILLs (counts-only — no
cumulative P&L). The report carries a prominent **multiple-comparisons caveat** (it states how
many strategies were tried) and emits **no winner/validation verdict** — corroboration on the
holdout is *suggestive, not proof*. The full set is always evaluated; cherry-picking a subset
after peeking would be the bias this guards against.

## Reading a report

Single-day reports begin with the `DATA WARNING`, then carry provenance (config hash, git
commit, ingest id, raw hash), bar counts, the quality summary, the opening range / strategy
context, an explicit `signal_bar_ts != fill_bar_ts` proof, **naive vs pessimistic** fills and
P&L, the friction-sweep grid + crossover, and a **verdict**:

| verdict | meaning |
|---|---|
| `PASS_FOR_MORE_TESTING` | pessimistic P&L survives the min-friction threshold |
| `HOLD_MORE_DATA` | inconclusive (no trade, or profitable only below the threshold) |
| `KILL_STRATEGY` | profitable on fantasy fills, loses under pessimistic fills |
| `INVALID_DATA` | quality thresholds failed |
| `INVALID_REPLAY` | lookahead or same-bar fill detected |

**Naive fills can never validate a strategy.** `decide_verdict` *requires* the pessimistic +
friction-sweep results — passing only naive numbers raises. PASS is granted only when
pessimistic P&L survives friction.

Every artifact is deterministic: `report_hash`, `aggregate_hash`, and `tournament_hash` cover
the analytical core only (levels, fills, P&L, sweep, verdict, config hash) and exclude
volatile provenance (wall-clock, paths, git commit, ids), so the same input reproduces the
same hash.

## Working with real data (Alpaca)

```bash
pip install -e ".[alpaca]"            # adds certifi so live TLS verifies (no manual SSL_CERT_FILE)
cp .env.example .env                  # then set ALPACA_API_KEY / ALPACA_SECRET_KEY
export ALPACA_API_KEY=... ALPACA_SECRET_KEY=...

# record a real session into a committed, replayable fixture (recommended):
python tools/record_real_day.py --symbol AAPL --date 2025-06-13   # -> fixtures/real_aapl_2025-06-13_iex.json
same-day-lab ingest --provider fixture --symbol AAPL --date 2025-06-13
same-day-lab run    --symbol AAPL --date 2025-06-13
```

The loader resolves a `(symbol, date)` to a recorded `real_<symbol>_<date>_iex.json` or a
known synthetic fixture, and **raises rather than silently serving the sample** for an
unmapped date. A handful of dates are reserved by synthetic fixtures (e.g. `2025-05-15`
sample, `2025-11-28` half-day, `2025-06-16` messy-real, plus the multi-day/tournament
synthetic days — see `same_day_lab/ingest/fixture.py`); pick any *other* real trading day for
a live pull. Without credentials, `--provider alpaca` fails gracefully and points you to
`--provider fixture`. The client requests `adjustment=raw`, maps `401/403/429`/empty to clear
messages, retries once on a 429, and is intentionally not exercised by the offline suite.

## Status & the finding so far

The pipeline is complete end-to-end: honest fills, no-lookahead replay, friction sweep,
per-day verdicts, multi-day aggregates, and a holdout tournament — with an offline test suite
and real AAPL sessions committed under `docs/real-days/`.

On the first real evaluation (AAPL; decide `2025-06-02..06-13`, holdout `06-17..06-27`),
**0 of 3 pre-registered strategies carried forward.** Two looked promising in-sample
(`vwap_reclaim` and `or_fade` cleared friction on ~50–57% of traded days) but **deflated
out-of-sample** (to ~38% and 29%). No corroborated edge — the holdout doing exactly its job.
A negative result, which is the point.

## Scope & non-goals

Each capability is built as the smallest working spike; over-delivery is the failure mode.
The lab deliberately has **no optimizer or parameter search, no live/forward execution, no
portfolio or position sizing, no shorting/leverage, no dynamic symbol universe, and no LLM in
the decision path.** Negative results ("the edge dies under friction") are deliverables, not
failures to paper over.

## Layout

```
same_day_lab/   ingest · storage · quality · replay · strategy · fills · reports · runner.py · cli.py
config/         default.yaml (all knobs; a stable config hash is recorded on every run)
fixtures/       synthetic + recorded-real 1-minute sessions (the default, offline provider)
tools/          gen_fixture.py, record_real_day.py
docs/prompts/   versioned build prompts          docs/real-days/   committed real-data results
```
