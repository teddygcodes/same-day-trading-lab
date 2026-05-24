"""Pessimistic fill simulation — the serious, default path.

This is the canonical path generator: it decides the entry bar, the exit bar, and
the exit reason, which the naive model then re-prices. Pessimism is encoded as:

  * Entry on the bar AFTER the signal, at ``max(next_open, trigger) + adverse``.
  * Exits only on bars strictly after the entry bar (no same-bar fills).
  * Targets must be exceeded (``high > target``), not merely touched.
  * If stop and target fall in the same bar, the stop wins.
  * A stop fills at the worse of the stop level and the bar's open (gap-through).
  * Otherwise flatten at the flatten bar's close.

P&L is per share (long only): exit - entry. Adverse slippage is cents + bps,
applied against you on both legs.
"""


def _buy_adverse(ref: float, cents: float, bps: float) -> float:
    """Long entry fills worse (higher)."""
    return ref + cents / 100.0 + ref * bps / 10000.0


def _sell_adverse(ref: float, cents: float, bps: float) -> float:
    """Long exit fills worse (lower)."""
    return ref - cents / 100.0 - ref * bps / 10000.0


def simulate_pessimistic(
    bars_after_signal,
    *,
    trigger_price: float,
    stop_price: float,
    flatten_ts,
    target_r_multiple: float,
    params,
) -> dict:
    if not bars_after_signal:
        raise ValueError("no bars after the signal; cannot fill an entry")

    entry_bar = bars_after_signal[0]
    entry_ref = max(entry_bar.open, trigger_price)
    entry = _buy_adverse(entry_ref, params.entry_cents, params.entry_bps)

    stop = stop_price
    target = entry + target_r_multiple * (entry - stop)

    exit_price = None
    exit_reason = None
    exit_bar_ts = None

    for bar in bars_after_signal[1:]:  # strictly after the entry bar
        stop_hit = bar.low <= stop
        target_hit = bar.high > target  # must move beyond, not merely touch

        if stop_hit:  # stop wins ambiguous bars
            raw = min(stop, bar.open)  # gap-through fills at the open, worse than stop
            exit_price = _sell_adverse(raw, params.exit_cents, params.exit_bps)
            exit_reason = "stop"
        elif target_hit:
            exit_price = _sell_adverse(target, params.exit_cents, params.exit_bps)
            exit_reason = "target"
        elif bar.bar_start_ts >= flatten_ts:
            exit_price = _sell_adverse(bar.close, params.exit_cents, params.exit_bps)
            exit_reason = "flatten"

        if exit_reason is not None:
            exit_bar_ts = bar.bar_start_ts
            break

    if exit_reason is None:  # ran out of bars before the flatten time
        last = bars_after_signal[-1]
        exit_price = _sell_adverse(last.close, params.exit_cents, params.exit_bps)
        exit_reason = "flatten"
        exit_bar_ts = last.bar_start_ts

    return {
        "pessimistic_entry": entry,
        "pessimistic_exit": exit_price,
        "pnl": exit_price - entry,
        "fill_bar_ts": entry_bar.bar_start_ts,
        "exit_bar_ts": exit_bar_ts,
        "exit_reason": exit_reason,
        "target": target,
        "stop": stop,
    }
