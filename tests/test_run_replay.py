from same_day_lab.config import load_config
from same_day_lab.ingest.fixture import load_fixture
from same_day_lab.ingest.normalize import build_session, normalize_bars
from same_day_lab.replay import run_replay
from tests.conftest import ladder, utc


def _fixture_rth():
    cfg = load_config()
    payload = load_fixture("AAPL", "2025-05-15")
    bars = normalize_bars(payload, cfg, provider="fixture")
    session = build_session(payload, bars, cfg)
    rth = [b for b in bars if b.is_regular_market_hours]
    return cfg, rth, session


def test_run_replay_produces_target_trade_with_distinct_fill_bar():
    cfg, rth, session = _fixture_rth()
    res = run_replay(rth, cfg, flatten_ts=session.flatten_ts)
    trade = res["trade"]
    assert res["replay_valid"] is True
    assert trade is not None
    assert trade.exit_reason == "target"
    # the heart of the lab: a signal never fills on its own bar
    assert trade.signal_bar_ts != trade.fill_bar_ts
    assert trade.naive_pnl >= trade.pessimistic_pnl
    assert res["crossover"]["crossover_cents"] == 5


def test_run_replay_no_signal_returns_no_trade():
    cfg = load_config()
    # 5 OR bars then a flat tail that never closes above the OR high -> no breakout
    bars = ladder(
        utc(h=13, minute=30),
        [(100.0, 100.2, 100.0, 100.1)] * 5 + [(100.1, 100.15, 100.05, 100.1)] * 10,
    )
    res = run_replay(bars, cfg, flatten_ts=utc(h=15, minute=59))
    assert res["signal"] is None
    assert res["trade"] is None
    assert res["replay_valid"] is True
