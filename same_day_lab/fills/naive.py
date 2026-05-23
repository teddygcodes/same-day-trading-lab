"""Naive fill — the labeled lie / baseline.

Naive does NOT run its own simulation. It re-prices the canonical (pessimistic)
path at zero slippage: entry at the trigger close, exit at the exact stop / target
/ flatten level. Because it uses a better entry and exact-level exits on the same
path, ``naive_pnl >= pessimistic_pnl`` by construction. Naive P&L is a fantasy and
can never, on its own, validate a strategy.
"""


def price_naive(*, trigger_price: float, canonical: dict, flatten_close: float) -> dict:
    reason = canonical["exit_reason"]
    if reason == "target":
        naive_exit = canonical["target"]
    elif reason == "stop":
        naive_exit = canonical["stop"]  # exact OR-low, zero slippage, no gap-through
    else:  # flatten
        naive_exit = flatten_close

    naive_entry = trigger_price
    return {
        "naive_entry": naive_entry,
        "naive_exit": naive_exit,
        "naive_pnl": naive_exit - naive_entry,
    }
