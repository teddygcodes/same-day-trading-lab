from datetime import timezone

from same_day_lab.config import load_config
from same_day_lab.ingest.fixture import load_fixture
from same_day_lab.ingest.normalize import build_session, normalize_bars


def test_normalize_rth_and_grid():
    cfg = load_config()
    payload = load_fixture("AAPL", "2025-05-15")
    bars = normalize_bars(payload, cfg, provider="fixture")
    assert len(bars) == 390
    assert all(b.bar_duration_seconds == 60 for b in bars)
    assert all(b.is_regular_market_hours for b in bars)        # full RTH day
    assert all(b.bar_start_ts.tzinfo == timezone.utc for b in bars)
    assert bars[0].bar_end_ts > bars[0].bar_start_ts
    # bars are sorted ascending by start
    assert bars == sorted(bars, key=lambda b: b.bar_start_ts)
    # 09:30 ET == 13:30Z
    assert bars[0].bar_start_ts.hour == 13 and bars[0].bar_start_ts.minute == 30


def test_build_session_full_day():
    cfg = load_config()
    payload = load_fixture("AAPL", "2025-05-15")
    bars = normalize_bars(payload, cfg, provider="fixture")
    session = build_session(payload, bars, cfg)
    assert session.is_half_day is False
    assert session.bar_count_expected == 390
    assert session.bar_count_actual == 390


def test_build_session_half_day():
    cfg = load_config()
    payload = load_fixture("AAPL", "2025-11-28")
    bars = normalize_bars(payload, cfg, provider="fixture")
    session = build_session(payload, bars, cfg)
    assert session.is_half_day is True
    assert session.bar_count_expected == 210
    assert session.bar_count_actual == 210
