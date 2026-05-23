# same-day-trading-lab

v0.1 — a deterministic historical-replay **fill-honesty lab** for intraday equity research.

> Full documentation is finalized at the end of the v0.1 build. See `config/default.yaml`
> for the knobs and `same_day_lab/` for the pipeline.

This is **not** a trading bot. It replays one symbol / one historical trading day of
1-minute bars behind a structural no-lookahead firewall, runs a 5-minute ORB-long smoke
test, and measures how much apparent P&L dies moving from fantasy (naive) fills to
pessimistic fills.
