from datetime import timedelta

from same_day_lab.models import Session
from same_day_lab.quality import flags
from tests.conftest import make_bar, utc


def test_suspicious_ohlc_fires_on_high_below_low():
    bad = make_bar(utc(), o=100.0, h=99.0, l=100.5, c=100.2)  # high < low
    assert flags.flag_suspicious_ohlc(bad) is True


def test_suspicious_ohlc_fires_on_close_outside_range():
    bad = make_bar(utc(), o=100.0, h=100.5, l=99.5, c=101.0)  # close > high
    assert flags.flag_suspicious_ohlc(bad) is True


def test_suspicious_ohlc_silent_on_clean():
    good = make_bar(utc(), o=100.0, h=100.5, l=99.5, c=100.2)
    assert flags.flag_suspicious_ohlc(good) is False


def test_zero_volume_fires_and_is_silent_when_positive():
    assert flags.flag_zero_volume(make_bar(utc(), 100, 100, 100, 100, v=0)) is True
    assert flags.flag_zero_volume(make_bar(utc(), 100, 100, 100, 100, v=5)) is False


def test_out_of_session_fires():
    assert flags.flag_out_of_session(make_bar(utc(), 100, 100, 100, 100, rth=False)) is True
    assert flags.flag_out_of_session(make_bar(utc(), 100, 100, 100, 100, rth=True)) is False


def _session(open_ts, close_ts, expected, actual, half=False):
    return Session(
        session_date="2025-05-15",
        symbol="AAPL",
        session_open_ts=open_ts,
        session_close_ts=close_ts,
        flatten_ts=close_ts - timedelta(minutes=1),
        is_half_day=half,
        bar_count_expected=expected,
        bar_count_actual=actual,
    )


def test_missing_bar_detected_on_60s_grid():
    open_ts = utc(h=13, minute=30)
    close_ts = utc(h=13, minute=35)  # expects 5 bars: 30,31,32,33,34
    bars = [
        make_bar(utc(h=13, minute=30), 100, 100, 100, 100),
        make_bar(utc(h=13, minute=31), 100, 100, 100, 100),
        # 13:32 missing
        make_bar(utc(h=13, minute=33), 100, 100, 100, 100),
        make_bar(utc(h=13, minute=34), 100, 100, 100, 100),
    ]
    missing = flags.find_missing_bars(bars, _session(open_ts, close_ts, 5, 4))
    assert [m.minute for m in missing] == [32]


def test_no_missing_on_complete_grid():
    open_ts = utc(h=13, minute=30)
    close_ts = utc(h=13, minute=33)
    bars = [make_bar(utc(h=13, minute=30 + i), 100, 100, 100, 100) for i in range(3)]
    assert flags.find_missing_bars(bars, _session(open_ts, close_ts, 3, 3)) == []


def test_duplicate_bar_detected():
    bars = [
        make_bar(utc(h=13, minute=30), 100, 100, 100, 100),
        make_bar(utc(h=13, minute=30), 100, 100, 100, 100),  # dup ts
        make_bar(utc(h=13, minute=31), 100, 100, 100, 100),
    ]
    dups = flags.find_duplicate_bars(bars)
    assert len(dups) == 1 and dups[0].minute == 30


def test_stale_repeat_fires_on_3_identical():
    bars = [make_bar(utc(h=13, minute=30 + i), 100, 100.1, 99.9, 100.05, v=500) for i in range(3)]
    runs = flags.find_stale_repeats(bars, min_consecutive=3)
    assert len(runs) == 1 and len(runs[0]) == 3


def test_stale_repeat_silent_on_two():
    bars = [make_bar(utc(h=13, minute=30 + i), 100, 100.1, 99.9, 100.05, v=500) for i in range(2)]
    assert flags.find_stale_repeats(bars, min_consecutive=3) == []


def test_extreme_move_fires_above_pct():
    # range / open * 100 = (106-100)/100*100 = 6% > 5%
    assert flags.flag_extreme_move(make_bar(utc(), 100.0, 106.0, 100.0, 105.0), 5.0) is True
    # 2% < 5%
    assert flags.flag_extreme_move(make_bar(utc(), 100.0, 102.0, 100.0, 101.0), 5.0) is False


def test_partial_session_fires_on_trailing_truncation():
    open_ts = utc(h=13, minute=30)
    close_ts = utc(h=14, minute=10)            # 40-min grid; last slot = 14:09
    missing = [open_ts + timedelta(minutes=m) for m in range(30, 40)]  # trailing run of 10 -> 14:09
    s = _session(open_ts, close_ts, expected=40, actual=30)
    assert flags.partial_session(missing, s, min_consecutive=10) is True


def test_partial_session_silent_on_interior_gap():
    open_ts = utc(h=13, minute=30)
    close_ts = utc(h=14, minute=10)
    missing = [open_ts + timedelta(minutes=m) for m in range(15, 25)]  # interior run of 10
    s = _session(open_ts, close_ts, expected=40, actual=30)
    assert flags.partial_session(missing, s, min_consecutive=10) is False


def test_halt_run_detected_interior_and_nonfatal():
    open_ts = utc(h=13, minute=30)
    close_ts = utc(h=14, minute=10)
    s = _session(open_ts, close_ts, expected=40, actual=30)
    missing = [open_ts + timedelta(minutes=m) for m in range(15, 25)]  # interior 10-run
    halts = flags.find_halt_runs(missing, s, min_consecutive=10)
    assert len(halts) == 1 and len(halts[0]) == 10


def test_halt_run_silent_on_scattered_and_on_edge():
    open_ts = utc(h=13, minute=30)
    close_ts = utc(h=14, minute=10)
    s = _session(open_ts, close_ts, expected=40, actual=36)
    scattered = [open_ts + timedelta(minutes=m) for m in (16, 20, 24, 28)]
    assert flags.find_halt_runs(scattered, s, min_consecutive=10) == []
    edge = [open_ts + timedelta(minutes=m) for m in range(30, 40)]  # trailing edge run
    assert flags.find_halt_runs(edge, s, min_consecutive=10) == []  # edge run is truncation, not halt
