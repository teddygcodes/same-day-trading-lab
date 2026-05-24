DATA WARNING:
This run may use Alpaca free/IEX feed bars. IEX represents only a subset of US
equity market volume. Reported volume is not consolidated-tape volume. Bar
highs/lows may exclude prints from other venues. No quote/spread data is present.
Spreads and fills are modeled, not observed. Do not interpret any P&L as achievable.

# same-day-trading-lab tournament — AAPL

- Decide window (in-sample, where we looked): **2025-06-02 → 2025-06-13**
- Holdout window (confirmatory, unseen): **2025-06-17 → 2025-06-27**
- Config hash: `80f1718a8e2907e2…`  Tournament hash: `df2addaeaf336af2…`

## ⚠ Multiple-comparisons caveat
**3 strategies evaluated; with 3 tries a single in-sample PASS is weak — corroboration on the holdout is required, and even that is suggestive, not proof.**

_Survives rule:_ A strategy survives a window iff, in that window, it traded at least 3 days, a strict majority (>50%) of those traded days are PASS_FOR_MORE_TESTING (cleared the friction-survival gate), and no day is a fill-honesty KILL_STRATEGY. The day floor and pass-fraction are pre-registered, a-priori honesty constants — fixed before looking and never tuned to the data. carried_forward = survives the decide window AND the holdout window.

## Leaderboard
| strategy | decide: traded | survived_pass | KILL | fill-honesty | survives | holdout: traded | survived_pass | KILL | fill-honesty | survives | carried_forward |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `or_fade_long` | 7 | 4 | 0 | 0 | True | 7 | 2 | 0 | 0 | False | **False** |
| `orb_long_5m` | 7 | 1 | 0 | 0 | False | 6 | 1 | 0 | 0 | False | **False** |
| `vwap_reclaim_long` | 10 | 5 | 0 | 0 | False | 8 | 3 | 0 | 0 | False | **False** |

## Missing weekdays — holdout (no ingest; record/ingest them, or holidays)
2025-06-19

_0 of 3 strategies carried forward (survived both windows). Descriptive only — not a verdict._

_Descriptive leaderboard only — no tournament winner or validation verdict. Per-strategy, per-day verdicts stand; corroboration on the holdout is suggestive, not proof._

