import pytest

from same_day_lab.replay import ReplayError, enforce_no_same_bar_fill
from tests.conftest import utc


def test_same_bar_fill_ban_raises_on_equal_ts():
    ts = utc(h=13, minute=40)
    with pytest.raises(ReplayError):
        enforce_no_same_bar_fill(signal_bar_ts=ts, fill_bar_ts=ts)


def test_same_bar_fill_ban_ok_when_next_bar():
    ts = utc(h=13, minute=40)
    ts_next = utc(h=13, minute=41)
    # must not raise
    enforce_no_same_bar_fill(signal_bar_ts=ts, fill_bar_ts=ts_next)
