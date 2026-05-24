# CLAUDE.md — same-day-trading-lab

Read this before doing anything. It encodes the non-negotiables. When the letter and
spirit of a request seem to conflict with these invariants, **stop and ask** rather
than quietly working around them.

## What this project is

A deterministic historical-replay **fill-honesty lab** for intraday equity research.
The whole point is to measure how much apparent P&L dies moving from fantasy (naive)
fills to pessimistic fills, on **1-minute bars, without lookahead**. ORB is only a
smoke-test subject, not a strategy we believe in.

It is **NOT** a trading bot, backtester-for-profit, optimizer, or dashboard. Paper
P&L is never trusted (a retired predecessor, "Bob", taught that lesson).

## Working model (roles)

- A **planning agent** (separate, human-directed) owns architecture and writes
  **build prompts** to `docs/prompts/`. If you are a coding session, your task comes
  from one of those prompts (or the user directly). Implement exactly that scope.
- Build the **smallest working spike**. Over-delivery is the failure mode. No
  abstractions for hypothetical future needs, no scope you weren't asked for.

## NEVER build (hard prohibitions)

Live/real-capital orders · broker execution · order routing · async / threading /
websockets · live forward data collection · dashboards / Streamlit / Gradio / any UI ·
dynamic or top-volume symbol universes · optimizers / grid search · a multi-strategy
*engine* · portfolio allocation · shorting / leverage / margin · overnight holds ·
tick/quote dependency · an LLM anywhere in the decision path · a generalized provider
framework · rich HTML reports. Do not add Sharpe/Sortino/annualized/equity-curve
metrics or marketing language to reports.

## NEVER violate (load-bearing invariants)

1. **No lookahead is structural, not disciplinary.** A strategy receives only a
   `ReplayView` of *completed* bars. `ReplayClock` owns the full series privately and
   advances one bar at a time. Never hand a strategy the full list/DB/dataframe, and
   never add a view method that returns a future bar.
2. **A signal on bar N fills no earlier than bar N+1.** `signal_bar_ts == fill_bar_ts`
   must be impossible; if detected, the run is `INVALID_REPLAY`.
3. **Pessimistic fills are the serious default path:** next-bar entry at
   `max(next_open, trigger) + adverse_slippage`; stop wins ambiguous bars; targets must
   be *exceeded* (`high > target`), not touched; a gapped stop fills worse than the
   stop level; otherwise flatten at the flatten time.
4. **Naive is a labeled lie** — a re-pricing of the *same* pessimistic path at zero
   slippage (entry at trigger close, exits at exact levels). The `trades` schema has a
   single exit-bar pair with dual prices, which *forces* this design. Keep
   `naive_pnl ≥ pessimistic_pnl` by construction.
5. **The verdict can never PASS on naive alone.** `decide_verdict` *requires* the
   pessimistic + friction-sweep results (passing `None` raises). PASS only when
   pessimistic P&L survives the min-friction threshold.
6. **Determinism:** `report_hash` covers only the analytical core (OR levels, fills,
   P&L, sweep, crossover, verdict, config hash) and excludes volatile provenance
   (wall-clock, file paths, git commit, ids). Same fixture + config ⇒ same hash. Add a
   determinism test for any new analytical output.
7. **Provenance:** archive the verbatim raw payload with a content hash *before*
   normalization; SQLite is the store; the **DATA WARNING** is the first block of every
   report. **Never fabricate or silently substitute data** — missing minutes are
   surfaced, never filled, and the fixture loader resolves a requested `(symbol, date)`
   to its recorded/known file or **raises**; it must not serve the sample day for an
   unmapped date.
8. **Time:** all stored timestamps are timezone-aware UTC, ISO-8601 with offset. The
   market timezone (`America/New_York`) is used only for session bounds and
   `reconstruct --time`. Convert via `zoneinfo` (DST matters — half-days are EST).
9. **Negative results are deliverables.** "The edge dies under friction" is a success,
   not a failure to paper over.

## Architecture (pipeline)

`ingest` (archive raw + hash) → `normalize` → SQLite → `quality` checks → no-lookahead
`replay` → `strategy/orb_long` (signal only) → `fills` (pessimistic canonical path +
naive re-pricing) → `fills/sweep` → `reports/writer` (JSON+MD) → `reports/verdict`.

Key modules: `replay/clock.py` + `replay/view.py` (firewall), `replay/__init__.py`
(`run_replay` orchestration + same-bar guard), `fills/pessimistic.py` (canonical path),
`runner.py` (`run_one_day` + `run_range`), `reports/verdict.py` (PASS gate),
`reports/aggregate.py` (descriptive multi-day rollup). CLI in `cli.py` only parses args
and dispatches.

## Quality gating (v0.2)

A run is `INVALID_DATA` on: suspicious OHLC, duplicate bars, missing RTH minutes beyond
`quality.missing_bar_policy.max_missing_fatal`, or a **partial session** (a leading or
trailing missing run that reaches a session edge with length ≥ `halt_run_min_consecutive`
— the feed never covered the full session). **Non-fatal** (flagged + surfaced, never
invalidating): missing minutes within tolerance, `halt_suspected` (an *interior*
consecutive-missing run), zero volume, extreme single-bar moves, stale repeats. IEX
legitimately omits no-trade minutes — that is why scattered gaps are non-fatal. Split/
adjustment detection is still deferred (needs multi-day prior-close context).

## Multi-day (v0.3)

`run-range` replays each ingested day **independently** (its own clock / opening range /
one-trade-per-day; no carry-over, no compounding, per-share P&L) and emits a
**descriptive aggregate**: counts, a crossover-cents distribution, and the fill-honesty
headline (days where naive looked profitable but pessimistic killed it), with a
deterministic `aggregate_hash`. It is **NOT a portfolio backtester** — no cumulative
P&L, equity curve, drawdown, or Sharpe/Sortino, and **no aggregate validation verdict**
(per-day verdicts stand). It runs only over ingested days, surfaces missing weekdays, and
never fabricates (no market-calendar dependency).

## Dev workflow

- **Python 3.11+. Stdlib-minimal**: argparse, dataclasses, sqlite3, zoneinfo, urllib.
  External deps are `pyyaml` + `tzdata` (core) and `pytest` (test extra); `certifi` is an
  optional `alpaca` extra (`pip install -e ".[alpaca]"`) that makes live pulls verify TLS
  without a manual `SSL_CERT_FILE`. Do not add others without a build prompt that says so.
- **TDD**: write a failing test → minimal implementation → green → commit. Small,
  frequent commits.
- **Tests must run offline.** No network in the suite. Fixtures (`fixtures/*.json`,
  regenerated by `tools/gen_fixture.py`) are the default provider. The live Alpaca path
  is intentionally untested offline.
- **Quality flags are pure functions** (no I/O) so they stay unit-testable.
- **Env gotcha:** if the editable install starts failing to import the package
  (`ModuleNotFoundError` from the console script while `python -m pytest` works), do
  NOT churn `pip uninstall`/reinstall or switch editable modes — `rm -rf .venv` and
  recreate it.

## Commands

```bash
pip install -e ".[test]" && pytest          # offline
same-day-lab init-db
same-day-lab ingest --provider fixture --symbol AAPL --date 2025-05-15
same-day-lab run     --symbol AAPL --date 2025-05-15
same-day-lab run-range --symbol AAPL --start 2025-07-07 --end 2025-07-11   # per-day independent + aggregate
same-day-lab report  --symbol AAPL --date 2025-05-15
same-day-lab reconstruct --symbol AAPL --date 2025-05-15 --time "10:32"   # --time is market tz
```

## Layout

`same_day_lab/{ingest,storage,quality,replay,strategy,fills,reports}/` · `config/default.yaml`
· `fixtures/` (sample, half-day, messy-real) · `tools/{gen_fixture,record_real_day}.py` ·
`tests/` · `docs/prompts/` (build prompts) · generated artifacts in `data/` and
`reports/` are gitignored.
