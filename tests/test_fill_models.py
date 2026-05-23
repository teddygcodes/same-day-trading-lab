from same_day_lab.fills.naive import price_naive
from same_day_lab.fills.pessimistic import simulate_pessimistic
from same_day_lab.fills.sweep import run_sweep
from same_day_lab.models import FillParams
from tests.conftest import make_bar, utc

FAR_FLATTEN = utc(h=15, minute=59)
CFG_PARAMS = FillParams(entry_cents=2, exit_cents=2, entry_bps=5, exit_bps=5)


def _entry_bar(o=100.20):
    return make_bar(utc(h=13, minute=41), o, o + 0.10, o - 0.05, o + 0.05)


def test_pessimistic_le_naive_on_controlled_path():
    entry = _entry_bar()
    after = [entry, make_bar(utc(h=13, minute=42), 100.30, 100.70, 100.30, 100.65)]  # target hit
    canon = simulate_pessimistic(
        after, trigger_price=100.25, or_high=100.20, or_low=100.00,
        flatten_ts=FAR_FLATTEN, r_multiple=1.0, params=CFG_PARAMS,
    )
    naive = price_naive(trigger_price=100.25, canonical=canon, flatten_close=after[-1].close)
    assert canon["exit_reason"] == "target"
    assert canon["pnl"] <= naive["naive_pnl"]
    # entry filled on the bar after the signal, never the signal bar
    assert canon["fill_bar_ts"] == entry.bar_start_ts


def test_stop_wins_when_stop_and_target_share_a_bar():
    entry = _entry_bar()
    # one bar where low pierces the stop (100.00) AND high clears the target
    after = [entry, make_bar(utc(h=13, minute=42), 100.30, 100.90, 99.95, 100.10)]
    canon = simulate_pessimistic(
        after, trigger_price=100.25, or_high=100.20, or_low=100.00,
        flatten_ts=FAR_FLATTEN, r_multiple=1.0, params=CFG_PARAMS,
    )
    assert canon["exit_reason"] == "stop"


def test_gap_through_stop_fills_worse_than_stop():
    entry = _entry_bar()
    # bar gaps open below the stop -> filled at the open, worse than the stop level
    after = [entry, make_bar(utc(h=13, minute=42), 99.90, 99.95, 99.80, 99.85)]
    canon = simulate_pessimistic(
        after, trigger_price=100.25, or_high=100.20, or_low=100.00,
        flatten_ts=FAR_FLATTEN, r_multiple=1.0, params=CFG_PARAMS,
    )
    assert canon["exit_reason"] == "stop"
    assert canon["pessimistic_exit"] < 100.00  # worse than the OR-low stop level


def test_target_requires_move_beyond_not_touch():
    # zero slippage so the target is a clean 101.00 (= entry + 1R, stop 99.00)
    p0 = FillParams(0, 0, 0, 0)
    entry = make_bar(utc(h=13, minute=41), 100.00, 100.05, 99.95, 100.00)
    touch = make_bar(utc(h=13, minute=42), 100.50, 101.00, 100.40, 100.90)  # high == target
    beyond = make_bar(utc(h=13, minute=43), 100.90, 101.01, 100.80, 101.00)  # high > target
    after = [entry, touch, beyond]
    canon = simulate_pessimistic(
        after, trigger_price=100.00, or_high=100.00, or_low=99.00,
        flatten_ts=FAR_FLATTEN, r_multiple=1.0, params=p0,
    )
    assert canon["target"] == 101.00
    assert canon["exit_reason"] == "target"
    assert canon["exit_bar_ts"] == beyond.bar_start_ts  # touch bar did NOT fill


def test_flatten_when_neither_stop_nor_target():
    entry = _entry_bar()
    # price drifts, never reaching target or stop, until the flatten bar
    flat_bar = make_bar(FAR_FLATTEN, 100.30, 100.35, 100.25, 100.30)
    after = [entry, make_bar(utc(h=13, minute=42), 100.30, 100.40, 100.25, 100.32), flat_bar]
    canon = simulate_pessimistic(
        after, trigger_price=100.25, or_high=100.20, or_low=100.00,
        flatten_ts=FAR_FLATTEN, r_multiple=1.0, params=CFG_PARAMS,
    )
    assert canon["exit_reason"] == "flatten"
    assert canon["exit_bar_ts"] == flat_bar.bar_start_ts


def test_sweep_table_and_crossover_shapes():
    entry = _entry_bar()
    after = [entry, make_bar(utc(h=13, minute=42), 100.30, 100.70, 100.30, 100.65)]
    table, crossover = run_sweep(
        after, trigger_price=100.25, or_high=100.20, or_low=100.00,
        flatten_ts=FAR_FLATTEN, r_multiple=1.0,
        cents_grid=[0, 1, 2, 5, 10], bps_grid=[0, 5, 10, 15], crossover_bps=5,
    )
    assert len(table) == 5 * 4
    assert {"cents", "bps", "pnl", "exit_reason"} <= set(table[0].keys())
    assert "crossover_cents" in crossover and "axis_bps" in crossover
    # higher friction never improves P&L along the crossover axis
    axis = sorted([r for r in table if r["bps"] == 5], key=lambda r: r["cents"])
    pnls = [r["pnl"] for r in axis]
    assert pnls == sorted(pnls, reverse=True)
