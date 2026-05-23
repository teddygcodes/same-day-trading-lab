"""Shared test helpers for building Bars and timestamps without a provider."""

from datetime import datetime, timedelta, timezone

from same_day_lab.models import Bar


def utc(y=2025, mo=5, m=15, h=13, minute=30):
    return datetime(y, mo, m, h, minute, tzinfo=timezone.utc)


def make_bar(
    start,
    o,
    h,
    l,
    c,
    *,
    v=1000.0,
    rth=True,
    symbol="AAPL",
    date="2025-05-15",
    provider="test",
    duration=60,
):
    return Bar(
        symbol=symbol,
        session_date=date,
        bar_start_ts=start,
        bar_end_ts=start + timedelta(seconds=duration),
        bar_duration_seconds=duration,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
        provider=provider,
        is_regular_market_hours=rth,
    )


def ladder(start, ohlc_list, *, step_minutes=1, **kw):
    """Build consecutive bars from a list of (o,h,l,c) tuples."""
    out = []
    t = start
    for (o, h, l, c) in ohlc_list:
        out.append(make_bar(t, o, h, l, c, **kw))
        t = t + timedelta(minutes=step_minutes)
    return out
