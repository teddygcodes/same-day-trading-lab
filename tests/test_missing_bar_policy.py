from datetime import timedelta

from same_day_lab.config import load_config
from same_day_lab.models import Session
from same_day_lab.quality.summary import evaluate
from tests.conftest import make_bar, utc

OPEN = utc(h=13, minute=30)            # 09:30 ET (EDT) 2025-05-15 -> 13:30Z
CLOSE = utc(h=20, minute=0)            # 16:00 ET -> 20:00Z ; 390-min grid


def _session():
    return Session(
        session_date="2025-05-15", symbol="AAPL",
        session_open_ts=OPEN, session_close_ts=CLOSE,
        flatten_ts=CLOSE - timedelta(minutes=1), is_half_day=False,
        bar_count_expected=390, bar_count_actual=0,
    )


def _bars(drop):
    return [
        make_bar(OPEN + timedelta(minutes=m), 100.0, 100.1, 99.9, 100.0, v=1000)
        for m in range(390) if m not in drop
    ]


def test_few_scattered_gaps_are_nonfatal_and_surfaced():
    _pb, summary, data_valid, reasons = evaluate(_bars({100, 150, 200, 250, 300}), _session(), load_config())
    assert data_valid is True and reasons == []
    assert summary["missing_bar_count"] == 5 and len(summary["missing_bars"]) == 5
    assert summary["halt_suspected"] is False


def test_missing_above_max_missing_fatal_is_invalid():
    _pb, summary, data_valid, reasons = evaluate(_bars(set(range(50, 360, 10))), _session(), load_config())
    assert summary["missing_bar_count"] == 31           # 31 scattered, non-consecutive, interior
    assert data_valid is False
    assert any("missing" in r.lower() for r in reasons)
    assert summary["partial_session"] is False          # fatal via count, not truncation
    assert summary["halt_suspected"] is False


def test_interior_halt_run_is_nonfatal():
    _pb, summary, data_valid, reasons = evaluate(_bars(set(range(100, 112))), _session(), load_config())
    assert data_valid is True                           # 12 consecutive interior <= max_missing_fatal
    assert summary["halt_suspected"] is True
    assert len(summary["halt_runs"]) == 1 and len(summary["halt_runs"][0]) == 12


def test_evaluate_does_not_fabricate_bars():
    drop = {100, 150, 200}
    bars = _bars(drop)
    _pb, summary, _v, _r = evaluate(bars, _session(), load_config())
    assert len(bars) == 390 - len(drop)                 # input untouched, gaps preserved
    assert summary["rth_bar_count"] == 390 - len(drop)
    assert summary["missing_bar_count"] == len(drop)
