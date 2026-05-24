DATA WARNING:
This run may use Alpaca free/IEX feed bars. IEX represents only a subset of US
equity market volume. Reported volume is not consolidated-tape volume. Bar
highs/lows may exclude prints from other venues. No quote/spread data is present.
Spreads and fills are modeled, not observed. Do not interpret any P&L as achievable.

# same-day-trading-lab aggregate — AAPL 2025-06-02 → 2025-06-13

- Config hash: `80f1718a8e2907e2…`  Aggregate hash: `b9dbad97debc84f1…`
- _Descriptive distribution only — no aggregate validation verdict. Per-day verdicts stand as-is; naive fills can never validate a strategy._

## Per-day
| date | data_valid | verdict | traded | exit | naive | pess_default | pess_pass | crossover_c |
|---|---|---|---|---|---|---|---|---|
| 2025-06-02 | True | HOLD_MORE_DATA | False | — | — | — | — | — |
| 2025-06-03 | True | PASS_FOR_MORE_TESTING | True | flatten | +0.7250 | +0.4770 | +0.4170 | — |
| 2025-06-04 | True | HOLD_MORE_DATA | True | stop | -1.6450 | -1.9435 | -2.0035 | 0 |
| 2025-06-05 | True | HOLD_MORE_DATA | True | stop | -1.0100 | -1.2582 | -1.3182 | 0 |
| 2025-06-06 | True | HOLD_MORE_DATA | False | — | — | — | — | — |
| 2025-06-09 | True | HOLD_MORE_DATA | True | stop | -1.1900 | -1.4346 | -1.4946 | 0 |
| 2025-06-10 | True | HOLD_MORE_DATA | True | flatten | -0.5000 | -0.7429 | -0.8029 | 0 |
| 2025-06-11 | True | HOLD_MORE_DATA | True | stop | -1.2300 | -1.4735 | -1.5335 | 0 |
| 2025-06-12 | True | HOLD_MORE_DATA | True | flatten | -0.2850 | -0.5242 | -0.5842 | 0 |
| 2025-06-13 | True | HOLD_MORE_DATA | False | — | — | — | — | — |

## Aggregate counts
- Days ingested: **10**  (INVALID_DATA 0, INVALID_REPLAY 0, no-signal 3, traded 7)
- Among traded: naive>0 **1**, pessimistic-default>0 **1**, survived pass-threshold **1**, KILL **0**
- Crossover (cents) distribution: {'none': 1, '0': 6}

## Fill-honesty headline
**0** day(s) where naive looked profitable but pessimistic fills killed it.

_7 of 10 ingested day(s) traded; naive looked profitable on 1, pessimistic + friction killed 0; 1 survived the pass threshold; 0 INVALID_DATA, 3 no-signal. No aggregate verdict._

