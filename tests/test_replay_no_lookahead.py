from datetime import timedelta

from same_day_lab.replay.clock import ReplayClock
from tests.conftest import make_bar, utc

POISON_PRICE = 999999.0


def _bars_with_poison(n=10, poison_index=5):
    bars = []
    for i in range(n):
        t = utc(h=13, minute=30 + i)
        if i == poison_index:
            bars.append(make_bar(t, POISON_PRICE, POISON_PRICE, POISON_PRICE, POISON_PRICE))
        else:
            bars.append(make_bar(t, 100.0, 100.1, 99.9, 100.0))
    return bars, poison_index


def test_view_never_exposes_future_bar():
    bars, poison_index = _bars_with_poison()
    clock = ReplayClock(bars)
    pos = 0
    while not clock.is_done():
        clock.advance()
        pos += 1
        view = clock.current_view()
        seen = view.completed_bars()
        assert len(seen) == pos
        if pos <= poison_index:
            # the poison bar is at index poison_index (0-based); not yet completed
            assert all(b.close != POISON_PRICE for b in seen)
        else:
            assert any(b.close == POISON_PRICE for b in seen)


def test_view_has_no_future_access_surface():
    bars, _ = _bars_with_poison()
    clock = ReplayClock(bars)
    clock.advance()
    view = clock.current_view()
    # Structural firewall: the view holds only completed bars, with no handle to
    # the clock or the full ordered store.
    assert not hasattr(view, "_clock")
    assert not hasattr(view, "all_bars")
    assert not hasattr(view, "future_bars")


def test_advancing_view_is_a_snapshot_not_a_live_handle():
    bars, _ = _bars_with_poison(n=4, poison_index=3)
    clock = ReplayClock(bars)
    clock.advance()
    early = clock.current_view()
    clock.advance()
    clock.advance()
    # A view captured earlier must not grow as the clock advances.
    assert early.bar_count() == 1
    assert clock.current_view().bar_count() == 3


def test_advance_returns_none_when_exhausted():
    bars = [make_bar(utc(h=13, minute=30 + i), 100, 100, 100, 100) for i in range(3)]
    clock = ReplayClock(bars)
    seen = [clock.advance() for _ in range(3)]
    assert all(b is not None for b in seen)
    assert clock.advance() is None
    assert clock.is_done()
