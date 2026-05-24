"""or_fade_long: failed-breakdown reclaim, long-only, one trade/day.

Opening range (first 5 RTH bars) = high 100.50 / low 100.00. The strategy fades a
*failed breakdown below* the OR low (a bear trap) — the mirror of ORB's breakout above
the OR high, so a pure breakout must NOT trigger it.
"""

from same_day_lab.replay.clock import ReplayClock
from same_day_lab.strategy.or_fade_long import OrFadeLongStrategy
from tests.conftest import make_bar, utc


def _run(strat, bars):
    clock = ReplayClock(bars)
    signals = []
    while not clock.is_done():
        clock.advance()
        s = strat.on_bar(clock.current_view())
        if s is not None:
            signals.append(s)
    return signals


def _bar(minute, close, *, low, high):
    return make_bar(utc(h=13, minute=minute), close, high, low, close)


def _or_bars():
    # 5 OR bars; OR high = 100.50, OR low = 100.00.
    return [_bar(30 + i, 100.20, low=100.00, high=100.50) for i in range(5)]


def test_breakdown_then_reclaim_fires_once():
    bars = _or_bars() + [
        _bar(35, 99.80, low=99.50, high=100.00),   # breakdown: close below OR low
        _bar(36, 100.10, low=99.70, high=100.20),  # reclaim: close back above OR low
    ]
    signals = _run(OrFadeLongStrategy(), bars)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.signal_bar_ts == utc(h=13, minute=36)
    assert sig.trigger_price == 100.10
    assert sig.stop_price == 99.50                  # lowest low of the breakdown swing
    assert sig.stop_price < 100.00 < sig.trigger_price  # stop below OR low, below entry
    assert sig.target_r_multiple == 1.0


def test_pure_breakout_above_or_high_does_not_fire():
    # closing above the OR high is ORB's trigger, not a failed breakdown -> or_fade silent.
    bars = _or_bars() + [_bar(35 + i, 100.80, low=100.60, high=101.00) for i in range(4)]
    assert _run(OrFadeLongStrategy(), bars) == []


def test_breakdown_without_reclaim_stays_silent():
    bars = _or_bars() + [
        _bar(35, 99.80, low=99.50, high=100.00),   # breakdown
        _bar(36, 99.70, low=99.40, high=99.90),    # stays below OR low
        _bar(37, 99.60, low=99.30, high=99.85),    # still below -> never reclaims
    ]
    assert _run(OrFadeLongStrategy(), bars) == []


def test_one_trade_per_day():
    bars = _or_bars() + [
        _bar(35, 99.80, low=99.50, high=100.00),   # breakdown
        _bar(36, 100.10, low=99.70, high=100.20),  # reclaim -> trade
        _bar(37, 99.70, low=99.40, high=99.90),    # breakdown again
        _bar(38, 100.15, low=99.60, high=100.25),  # reclaim again -> ignored
    ]
    signals = _run(OrFadeLongStrategy(), bars)
    assert len(signals) == 1
    assert signals[0].signal_bar_ts == utc(h=13, minute=36)
