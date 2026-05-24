# same-day-trading-lab

**v0.1 — a deterministic historical-replay _fill-honesty lab_ for intraday equity research.**

The narrow question v0.1 answers:

> Can we replay a same-day equity strategy on historical 1-minute bars **without
> lookahead**, and measure how much apparent P&L dies moving from fantasy fills to
> pessimistic fills?

## What this is / is not

It **is** a truth engine: one symbol, one historical trading day, one strategy, two
fill models, one deterministic report, and a verdict that **cannot PASS on fantasy
fills alone**.

It is **not** a trading bot, broker-execution system, strategy optimizer, dashboard,
AI trader, or a proof that ORB works. There is no live order code, no async, no
threading, no websockets, no UI, no multi-symbol universe, no optimizer.

## Why this lab exists (the retired predecessors)

Two predecessors were retired. **Glint** (a Kalshi paper bot) taught that the value
was *discipline* — deterministic math, full observability, raw archival, negative
results as deliverables. **Bob** (an Alpaca equity paper bot) produced paper P&L that
is **not trusted**: paper fills are not truth. This lab does not copy Bob's execution
loop or treat any paper fill as achievable. A future bot may only ever execute what
the lab approves — and v0.1 approves nothing; it just measures friction honestly.

## Why 1-minute bars deceive

A 1-minute OHLCV bar does **not** reveal what was tradeable inside the minute: not
whether the high preceded the low, whether a breakout preceded its stop, what size
traded at the high, what the spread was, or whether a real order would have filled.
So the breakout strategy here is only a **smoke-test subject**. The real deliverable
is honest fill modeling.

### Data provenance

Every report begins with a verbatim **DATA WARNING**: Alpaca's free/IEX feed is a
*subset* of US volume, bar highs/lows may exclude other venues, there is no
quote/spread data, and **spreads and fills are modeled, not observed**. Do not
interpret any P&L as achievable.

## Setup

Requires Python 3.11+.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest                       # all tests run offline, no network
```

### With fixtures (default, offline)

Fixtures live in `fixtures/` and are the default provider. No credentials needed.

### With Alpaca (optional, real IEX historical bars)

Set creds, then either ingest directly or — recommended — **record a real day into an
offline fixture** so the run is reproducible and the suite stays offline:

```bash
pip install -e ".[alpaca]"   # installs certifi so live pulls verify TLS (no SSL_CERT_FILE needed)
cp .env.example .env         # then set ALPACA_API_KEY / ALPACA_SECRET_KEY
export ALPACA_API_KEY=...  ALPACA_SECRET_KEY=...

# one-shot live ingest:
same-day-lab ingest --provider alpaca --symbol AAPL --date 2025-06-13

# or record-and-replay (capture the real day, then replay it offline):
python tools/record_real_day.py --symbol AAPL --date 2025-06-13   # -> fixtures/real_aapl_2025-06-13_iex.json
same-day-lab ingest --provider fixture --symbol AAPL --date 2025-06-13
same-day-lab run     --symbol AAPL --date 2025-06-13
```

The fixture loader resolves a `(symbol, date)` to a recorded `real_<symbol>_<date>_iex.json`
(or a known synthetic fixture) and **raises rather than silently serving the sample** for
an unmapped date. The synthetic fixture dates — `2025-05-15` (sample), `2025-06-16`
(messy-real), `2025-07-07`…`2025-07-10` (v0.3 multi-day mix), `2025-11-28` (half-day) —
are reserved; pick any *other* real trading day for a real pull.

If creds are missing, `--provider alpaca` fails gracefully and tells you to use
`--provider fixture`. The Alpaca client sends `adjustment=raw`, maps 401/403/429/empty to
clear messages, and retries once on a 429. The live HTTP path is intentionally not
covered by the offline test suite.

## Commands

```bash
same-day-lab init-db                                              # create the SQLite schema
same-day-lab ingest --provider fixture --symbol AAPL --date 2025-05-15
same-day-lab run     --symbol AAPL --date 2025-05-15              # replay + ORB + dual fills + report
same-day-lab report  --symbol AAPL --date 2025-05-15              # locate the latest report
same-day-lab reconstruct --symbol AAPL --date 2025-05-15 --time "10:32"
```

`reconstruct --time` is a **wall-clock time in the market timezone**
(`America/New_York`), converted to UTC for bar lookup. It shows what the system knew
at that instant (completed-bar count, last bar, quality summary) and verifies the
archived raw payload's hash.

## The pipeline

`ingest` (archive raw + content hash) → normalize → SQLite → quality checks →
no-lookahead replay → 5-minute ORB-long smoke test → dual fills → friction sweep →
deterministic JSON + Markdown report → verdict.

- **No-lookahead firewall:** the `ReplayClock` owns all bars privately and advances
  one at a time; a strategy only ever receives a `ReplayView` of *completed* bars,
  with no method that returns a future bar. A signal on bar N fills no earlier than
  bar N+1 — `signal_bar_ts == fill_bar_ts` raises and invalidates the run.
- **Pessimistic fills (the serious path):** enter on the next bar at
  `max(next_open, trigger) + adverse slippage`; stop wins ambiguous bars; targets
  must be *exceeded*, not touched; a gapped stop fills worse than the stop level;
  otherwise flatten at the flatten time.
- **Naive fills (a labeled lie):** the **same** path re-priced at zero slippage —
  entry at the trigger close, exits at exact levels. By construction
  `naive_pnl ≥ pessimistic_pnl`.
- **Friction sweep:** re-runs the pessimistic simulation across a cents × bps grid
  and reports the **crossover** — the friction at which pessimistic P&L turns
  non-positive.

## Data quality

Real IEX data legitimately omits no-trade minutes, so v0.1's "zero missing bars" rule is
replaced by a tolerance policy (`config/default.yaml` → `quality.missing_bar_policy`):

- **Missing RTH minutes** are non-fatal up to `max_missing_fatal` (default 30); beyond
  that the run is `INVALID_DATA`. The count and timestamps are surfaced in every report.
- **`halt_suspected`** — an *interior* consecutive-missing run ≥ `halt_run_min_consecutive`
  (default 10) — is flagged but **non-fatal**.
- **`partial_session`** — a leading/trailing missing run reaching a session edge — means
  the feed never covered the full session, and stays **fatal**.
- Suspicious OHLC and duplicate bars are always fatal. **Bars are never fabricated** to
  fill gaps. (Split/adjustment detection is deferred — it needs multi-day context.)

The `messy_real_aapl_1m.json` fixture (scattered gaps, an interior halt run, an
extreme-move bar, a zero-volume bar) exercises this end-to-end and still replays to a
deterministic, non-fatal report.

## How to read the report

Top of every report: the DATA WARNING. Then provenance (config hash, git commit,
ingest id, raw hash), bar counts, quality summary, the opening range, an explicit
`signal_bar_ts != fill_bar_ts` proof, **naive vs pessimistic** fills and P&L, the
friction-sweep grid + crossover, and the **verdict**:

| Verdict | Meaning |
|---|---|
| `PASS_FOR_MORE_TESTING` | pessimistic P&L survives the min-friction threshold |
| `HOLD_MORE_DATA` | inconclusive (e.g. no trade, or profitable only below the threshold) |
| `KILL_STRATEGY` | profitable on fantasy fills, loses under pessimistic fills |
| `INVALID_DATA` | quality thresholds failed |
| `INVALID_REPLAY` | lookahead or same-bar fill detected |

**Why naive fills cannot validate a strategy:** the verdict function *requires* the
pessimistic and friction-sweep results — passing only naive numbers raises. A PASS is
granted only when pessimistic P&L survives friction. Fantasy P&L can never, by
itself, produce a PASS.

`report_hash` covers only the analytical core (OR levels, fills, P&L, sweep,
crossover, verdict, config hash) and excludes volatile provenance, so the same
fixture + config always reproduces the same hash.

## Strategies

Strategies are **pre-registered hypotheses with fixed rules — never tuned or optimized**
(searching parameters until something "works" is the trap this lab exists to resist). Each
emits a generic `TradePlan` (entry trigger + stop + target-R) that the shared, honest fill
engine prices. Pick one with `--strategy` on `run` / `run-range` (default `orb_long_5m`).
All are **long-only**:

- **`orb_long_5m`** — opening-range breakout (close above the 5-min OR high; stop = OR low).
- **`vwap_reclaim_long`** — price reclaims the cumulative session VWAP from below (VWAP
  computed only from completed bars; stop = lowest low since the open).
- **`or_fade_long`** — a failed breakdown below the OR low that closes back above it
  (bear-trap reclaim; stop = the breakdown swing low).

```bash
same-day-lab run --symbol AAPL --date 2025-06-13 --strategy vwap_reclaim_long
```

## Multi-day (run-range)

Replay the same symbol + strategy across a date range, **each day independent** (its own
opening range and single trade — no carry-over, no compounding):

```bash
# each day must be ingested first (record_real_day + ingest, or a synthetic fixture)
same-day-lab run-range --symbol AAPL --start 2025-07-07 --end 2025-07-11
```

The aggregate (`reports/<symbol>_<start>_<end>_aggregate.{json,md}`) is a **descriptive
distribution, not a track record**: a per-day table, counts (traded / no-signal /
INVALID_DATA, naive>0, survived-friction, KILL), a crossover-cents distribution, and the
**fill-honesty headline** — how many days naive looked profitable but pessimistic fills
killed it. There is **no aggregate verdict** (per-day verdicts stand) and **no portfolio
math** (no equity curve, drawdown, or Sharpe). Weekdays in the range with no ingest are
listed as *missing* (record them, or they were holidays — there is no market calendar).
`aggregate_hash` makes the rollup deterministic.

## Why v0.1 is intentionally tiny

One symbol, one day, one strategy, two fill models, one report. The point is to nail
fill honesty and no-lookahead replay end-to-end — not to chase scope. Over-delivery
is the failure mode.
