"""Replay package: no-lookahead clock/view, the same-bar fill ban, and the
``run_replay`` orchestration."""


class ReplayError(Exception):
    """Raised when the replay invariant is violated (e.g. a same-bar fill)."""


def enforce_no_same_bar_fill(*, signal_bar_ts, fill_bar_ts) -> None:
    """A signal on bar N must fill no earlier than bar N+1.

    ``signal_bar_ts == fill_bar_ts`` is structurally impossible in a correct
    replay; if it ever occurs we fail the run rather than report fantasy fills.
    """
    if signal_bar_ts == fill_bar_ts:
        raise ReplayError(f"same-bar fill detected: signal and fill both at {signal_bar_ts}")


def run_replay(rth_bars, config, *, flatten_ts, strategy=None) -> dict:
    """Replay one RTH session: drive the selected strategy behind the firewall, fill
    the one trade (if any) both ways, and run the friction sweep.

    Returns a dict with ``strategy`` (the registered name), ``signal`` (TradePlan |
    None), ``trade`` (CanonicalTrade | None), ``strategy_context`` (small dict | None),
    ``crossover``, and ``replay_valid``. ``flatten_ts`` is provided by the caller (from
    the stored session) so this package needs no dependency on ingest.
    """
    from ..fills.naive import price_naive
    from ..fills.pessimistic import simulate_pessimistic
    from ..fills.sweep import run_sweep
    from ..models import CanonicalTrade, FillParams
    from ..strategy import DEFAULT_STRATEGY, get_strategy
    from .clock import ReplayClock

    strategy = strategy or DEFAULT_STRATEGY
    clock = ReplayClock(rth_bars)
    strat = get_strategy(strategy).from_config(config)
    signal = None
    while not clock.is_done():
        clock.advance()
        emitted = strat.on_bar(clock.current_view())
        if emitted is not None and signal is None:
            signal = emitted

    context = strat.strategy_context()
    base = {"strategy": strategy, "signal": signal, "trade": None,
            "strategy_context": context, "crossover": None, "replay_valid": True}

    if signal is None:
        return base

    idx = next(i for i, b in enumerate(rth_bars) if b.bar_start_ts == signal.signal_bar_ts)
    bars_after = rth_bars[idx + 1:]
    if not bars_after:  # signal on the last bar: no entry bar to fill on
        base["notes"] = "signal on last bar; no entry bar available — no trade"
        return base

    fp = config["fills"]["pessimistic"]
    params = FillParams(
        entry_cents=fp["entry_slippage_cents"], exit_cents=fp["exit_slippage_cents"],
        entry_bps=fp["entry_slippage_bps"], exit_bps=fp["exit_slippage_bps"],
    )
    canonical = simulate_pessimistic(
        bars_after, trigger_price=signal.trigger_price, stop_price=signal.stop_price,
        flatten_ts=flatten_ts, target_r_multiple=signal.target_r_multiple, params=params,
    )

    try:
        enforce_no_same_bar_fill(
            signal_bar_ts=signal.signal_bar_ts, fill_bar_ts=canonical["fill_bar_ts"]
        )
    except ReplayError as exc:
        base["replay_valid"] = False
        base["notes"] = str(exc)
        return base

    flat_bar = next((b for b in bars_after if b.bar_start_ts == flatten_ts), bars_after[-1])
    naive = price_naive(
        trigger_price=signal.trigger_price, canonical=canonical, flatten_close=flat_bar.close
    )

    fsw = config["fills"]["friction_sweep"]
    table, crossover = run_sweep(
        bars_after, trigger_price=signal.trigger_price, stop_price=signal.stop_price,
        flatten_ts=flatten_ts, target_r_multiple=signal.target_r_multiple,
        cents_grid=fsw["cents"], bps_grid=fsw["bps"], crossover_bps=fp["exit_slippage_bps"],
    )

    trade = CanonicalTrade(
        or_high=(context or {}).get("or_high"),
        or_low=(context or {}).get("or_low"),
        signal_bar_ts=signal.signal_bar_ts,
        fill_bar_ts=canonical["fill_bar_ts"],
        exit_signal_bar_ts=canonical["exit_bar_ts"],
        exit_fill_bar_ts=canonical["exit_bar_ts"],
        trigger_price=signal.trigger_price,
        naive_entry_price=naive["naive_entry"],
        naive_exit_price=naive["naive_exit"],
        naive_pnl=naive["naive_pnl"],
        pessimistic_entry_price=canonical["pessimistic_entry"],
        pessimistic_exit_price=canonical["pessimistic_exit"],
        pessimistic_pnl=canonical["pnl"],
        exit_reason=canonical["exit_reason"],
        friction_sweep=table,
        notes={"target_price": canonical["target"], "stop_price": canonical["stop"]},
    )
    base.update({"trade": trade, "crossover": crossover})
    return base
