"""vwap_reclaim_long: cumulative-VWAP reclaim, long-only, one trade/day, no lookahead.

All bars carry equal volume and vwap=100.0, so the cumulative session VWAP is a flat
100.0 throughout — the trigger then depends only on each bar's *close* crossing it.
"""

from same_day_lab.replay.clock import ReplayClock
from same_day_lab.strategy.vwap_reclaim_long import VwapReclaimLongStrategy
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


def _bar(minute, close, *, low):
    # high comfortably above close; vwap flat at 100 so cumulative VWAP stays 100.
    return make_bar(utc(h=13, minute=minute), close, close + 0.5, low, close, vw=100.0, v=1000.0)


def _warmup():
    # 5 RTH warmup bars sitting on the VWAP (close == 100.0).
    return [_bar(30 + i, 100.0, low=99.5) for i in range(5)]


def test_reclaim_fires_once_after_dip_below_vwap():
    # bar6 closes below VWAP (a real dip), bar7 closes back above -> reclaim.
    bars = _warmup() + [_bar(35, 99.0, low=98.5), _bar(36, 100.5, low=99.8)]
    signals = _run(VwapReclaimLongStrategy(), bars)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.signal_bar_ts == utc(h=13, minute=36)   # the reclaim bar
    assert sig.trigger_price == 100.5
    assert sig.stop_price == 98.5                       # lowest low since session open
    assert sig.stop_price < sig.trigger_price           # long requires stop below entry
    assert sig.target_r_multiple == 1.0


def test_no_reclaim_when_price_never_dips_below_vwap():
    # price holds above the VWAP the whole session -> no prior-bar-below, never fires.
    bars = _warmup() + [_bar(35 + i, 100.5, low=100.1) for i in range(4)]
    assert _run(VwapReclaimLongStrategy(), bars) == []


def test_silent_until_the_reclaim_bar_completes():
    # given only the dip (no reclaim bar yet) the strategy must stay silent: it reads
    # only completed bars and cannot peek ahead to the reclaim.
    pre_reclaim = _warmup() + [_bar(35, 99.0, low=98.5)]
    assert _run(VwapReclaimLongStrategy(), pre_reclaim) == []


def test_one_trade_per_day():
    # a second dip+reclaim after the first trade is ignored.
    bars = _warmup() + [
        _bar(35, 99.0, low=98.5),    # dip
        _bar(36, 100.5, low=99.8),   # reclaim -> trade
        _bar(37, 99.0, low=98.0),    # dip again
        _bar(38, 100.6, low=99.0),   # reclaim again -> must be ignored
    ]
    signals = _run(VwapReclaimLongStrategy(), bars)
    assert len(signals) == 1
    assert signals[0].signal_bar_ts == utc(h=13, minute=36)
