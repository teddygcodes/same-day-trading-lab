"""Normalize provider payloads (Alpaca-shaped bar dicts) into internal Bar models.

Both the fixture and Alpaca providers emit the same bar-dict keys
(``t,o,h,l,c,v,vw,n``) so a second provider could be added later without
touching downstream code.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..models import Bar, Session

HALF_DAY_CLOSE = "13:00"  # US half-day regular close (ET)


def _parse_ts(s: str) -> datetime:
    """Parse an RFC3339 instant (``...Z`` or offset) into a UTC datetime."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc)


def _local_to_utc(date: str, hhmm: str, tz: ZoneInfo) -> datetime:
    y, mo, d = (int(x) for x in date.split("-"))
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(y, mo, d, h, m, tzinfo=tz).astimezone(timezone.utc)


def market_time_to_utc(date: str, hhmm: str, config: dict) -> datetime:
    """Convert a wall-clock ``HH:MM`` in the configured market timezone to UTC."""
    return _local_to_utc(date, hhmm, ZoneInfo(config["market_timezone"]))


def session_bounds(payload: dict, config: dict) -> dict:
    """Resolve session open/close/flatten (UTC) and the expected RTH bar count.

    ``close`` is half-day-aware: a payload that declares ``is_half_day`` closes at
    13:00 ET, so the expected grid is shorter and a complete half-day is not flagged
    as a partial session.
    """
    tz = ZoneInfo(config["market_timezone"])
    date = payload["session_date"]
    sess = config["session"]
    is_half_day = bool(payload.get("is_half_day", False))
    open_utc = _local_to_utc(date, sess["regular_open"], tz)
    close_hhmm = HALF_DAY_CLOSE if is_half_day else sess["regular_close"]
    close_utc = _local_to_utc(date, close_hhmm, tz)
    flatten_utc = _local_to_utc(date, sess["flatten_time"], tz)
    expected = int((close_utc - open_utc).total_seconds() // 60)
    return {
        "open": open_utc,
        "close": close_utc,
        "flatten": flatten_utc,
        "is_half_day": is_half_day,
        "expected_count": expected,
    }


def normalize_bars(payload: dict, config: dict, *, provider: str) -> list[Bar]:
    b = session_bounds(payload, config)
    feed = payload.get("feed")
    symbol = payload["symbol"]
    date = payload["session_date"]
    duration = int(config["quality"]["expected_bar_seconds"])

    bars: list[Bar] = []
    for d in payload["bars"]:
        start = _parse_ts(d["t"])
        bars.append(
            Bar(
                symbol=symbol,
                session_date=date,
                bar_start_ts=start,
                bar_end_ts=start + timedelta(seconds=duration),
                bar_duration_seconds=duration,
                open=float(d["o"]),
                high=float(d["h"]),
                low=float(d["l"]),
                close=float(d["c"]),
                volume=float(d["v"]),
                vwap=(float(d["vw"]) if d.get("vw") is not None else None),
                trade_count=(int(d["n"]) if d.get("n") is not None else None),
                provider=provider,
                feed=feed,
                is_regular_market_hours=(b["open"] <= start < b["close"]),
            )
        )
    bars.sort(key=lambda x: x.bar_start_ts)
    return bars


def build_session(payload: dict, bars: list[Bar], config: dict) -> Session:
    b = session_bounds(payload, config)
    actual = sum(1 for x in bars if x.is_regular_market_hours)
    return Session(
        session_date=payload["session_date"],
        symbol=payload["symbol"],
        session_open_ts=b["open"],
        session_close_ts=b["close"],
        flatten_ts=b["flatten"],
        is_half_day=b["is_half_day"],
        bar_count_expected=b["expected_count"],
        bar_count_actual=actual,
    )
