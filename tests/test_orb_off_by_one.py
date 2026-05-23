from same_day_lab.replay.clock import ReplayClock
from same_day_lab.strategy.orb_long import OrbLongStrategy
from tests.conftest import make_bar, utc

CFG = {"opening_range_minutes": 5}


def _run(strat, bars):
    clock = ReplayClock(bars)
    signals = []
    while not clock.is_done():
        clock.advance()
        s = strat.on_bar(clock.current_view())
        if s is not None:
            signals.append(s)
    return signals


def _or_bars():
    # 5 opening-range bars; OR high = 100.50, OR low = 100.00
    return [
        make_bar(utc(h=13, minute=30), 100.05, 100.20, 100.00, 100.10),
        make_bar(utc(h=13, minute=31), 100.10, 100.30, 100.05, 100.20),
        make_bar(utc(h=13, minute=32), 100.20, 100.40, 100.10, 100.30),
        make_bar(utc(h=13, minute=33), 100.30, 100.45, 100.20, 100.40),
        make_bar(utc(h=13, minute=34), 100.40, 100.50, 100.30, 100.48),
    ]


def test_fifth_or_bar_cannot_trigger():
    # The 5th OR bar closes (100.80) above the high of the first four (100.45),
    # but it defines the range and must NOT itself trigger.
    bars = _or_bars()[:4] + [make_bar(utc(h=13, minute=34), 100.40, 100.90, 100.30, 100.80)]
    strat = OrbLongStrategy(CFG)
    signals = _run(strat, bars)
    assert signals == []
    assert strat.opening_range.high == max(b.high for b in bars)   # 5th bar is in the OR
    assert strat.opening_range.low == min(b.low for b in bars)


def test_trigger_on_sixth_bar_close_above_or_high():
    bars = _or_bars() + [make_bar(utc(h=13, minute=35), 100.48, 100.70, 100.45, 100.60)]
    strat = OrbLongStrategy(CFG)
    signals = _run(strat, bars)
    assert len(signals) == 1
    assert signals[0].signal_bar_ts == utc(h=13, minute=35)
    assert signals[0].trigger_price == 100.60


def test_high_break_without_close_above_does_not_trigger():
    # 6th bar's HIGH pierces OR high but its CLOSE stays at/below it -> no trigger.
    bars = _or_bars() + [make_bar(utc(h=13, minute=35), 100.48, 100.90, 100.45, 100.50)]
    strat = OrbLongStrategy(CFG)
    assert _run(strat, bars) == []


def test_one_trade_per_day():
    bars = _or_bars() + [
        make_bar(utc(h=13, minute=35), 100.48, 100.70, 100.45, 100.60),  # trigger
        make_bar(utc(h=13, minute=36), 100.60, 100.90, 100.55, 100.80),  # also above -> ignored
    ]
    strat = OrbLongStrategy(CFG)
    signals = _run(strat, bars)
    assert len(signals) == 1
    assert signals[0].signal_bar_ts == utc(h=13, minute=35)


def test_no_signal_before_or_complete():
    strat = OrbLongStrategy(CFG)
    signals = _run(strat, _or_bars()[:4])  # only 4 bars, OR never completes
    assert signals == []
    assert strat.opening_range is None
