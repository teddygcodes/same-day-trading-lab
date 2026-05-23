"""Friction sweep — re-run the pessimistic simulation across a cents x bps grid.

Each grid point applies the same friction to both the entry and exit legs and
re-runs the FULL simulation (entry slippage shifts the target, which can change
which bar the trade exits on — so this is a true re-simulation, not a re-pricing).

The crossover is reported along the cents axis at a fixed bps (the config
pessimistic bps): the smallest cents where pessimistic P&L turns non-positive.
A profitable result even at max friction is NOT proof of edge.
"""

from ..models import FillParams
from .pessimistic import simulate_pessimistic


def run_sweep(
    bars_after_signal,
    *,
    trigger_price: float,
    or_high: float,
    or_low: float,
    flatten_ts,
    r_multiple: float,
    cents_grid,
    bps_grid,
    crossover_bps: int,
) -> tuple[list, dict]:
    table = []
    for b in bps_grid:
        for c in cents_grid:
            res = simulate_pessimistic(
                bars_after_signal,
                trigger_price=trigger_price,
                or_high=or_high,
                or_low=or_low,
                flatten_ts=flatten_ts,
                r_multiple=r_multiple,
                params=FillParams(entry_cents=c, exit_cents=c, entry_bps=b, exit_bps=b),
            )
            table.append(
                {"cents": c, "bps": b, "pnl": round(res["pnl"], 6), "exit_reason": res["exit_reason"]}
            )
    return table, _crossover(table, crossover_bps)


def _crossover(table, crossover_bps) -> dict:
    axis = sorted([r for r in table if r["bps"] == crossover_bps], key=lambda r: r["cents"])
    crossover_cents = next((r["cents"] for r in axis if r["pnl"] <= 0), None)
    return {
        "axis_bps": crossover_bps,
        "crossover_cents": crossover_cents,
        "profitable_at_zero_cents": bool(axis and axis[0]["pnl"] > 0),
        "profitable_at_max_cents": bool(axis and axis[-1]["pnl"] > 0),
    }


def pnl_at(table, *, cents, bps):
    """Look up the swept pessimistic P&L at a specific (cents, bps) grid point."""
    for r in table:
        if r["cents"] == cents and r["bps"] == bps:
            return r["pnl"]
    return None
