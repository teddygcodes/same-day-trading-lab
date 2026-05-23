"""One-off generator for the committed test fixtures (convenience, not elegant).

Produces two deterministic Alpaca-shaped 1-minute payloads:

  fixtures/sample_aapl_1m_day.json  - full RTH day (390 bars). A small-edge
      ORB-long setup: opening range 100.00-100.20; breakout closes 100.25 at
      13:40Z; the unique post-entry peak high is 100.70 at 13:49Z. With the
      config friction (2c/5bps) the target is hit (profit ~0.25/share); at the
      5-cent pass threshold the rising entry pushes the target above 100.70 so
      the trade flattens at a loss -> the friction sweep crosses zero at 5c.

  fixtures/half_day_aapl_1m.json     - declared half-day (210 bars, 13:30-16:59Z).

Run:  python tools/gen_fixture.py
"""

import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
ET = ZoneInfo("America/New_York")


def _open_utc(date_str: str):
    """09:30 America/New_York on the given date, as UTC (DST-correct)."""
    y, m, d = (int(x) for x in date_str.split("-"))
    return datetime(y, m, d, 9, 30, tzinfo=ET).astimezone(timezone.utc)


def _bar(t, o, h, l, c, v=5000, n=42):
    return {
        "t": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "o": round(o, 2),
        "h": round(h, 2),
        "l": round(l, 2),
        "c": round(c, 2),
        "v": v,
        "vw": round((o + h + l + c) / 4, 2),
        "n": n,
    }


# Explicit bars (minute offset from 13:30Z) for the opening range, the pre-trigger
# lull, the breakout, the entry bar, and the climb to the unique 100.70 peak.
EXPLICIT = {
    0: (100.05, 100.15, 100.00, 100.10),   # opening range (5 bars)
    1: (100.10, 100.20, 100.05, 100.15),
    2: (100.15, 100.18, 100.08, 100.12),
    3: (100.12, 100.19, 100.05, 100.14),
    4: (100.14, 100.20, 100.02, 100.16),   # OR high=100.20, OR low=100.00
    5: (100.16, 100.20, 100.12, 100.18),   # lull: closes never exceed OR high
    6: (100.18, 100.20, 100.14, 100.19),
    7: (100.19, 100.20, 100.13, 100.17),
    8: (100.17, 100.20, 100.12, 100.18),
    9: (100.18, 100.20, 100.15, 100.19),
    10: (100.19, 100.27, 100.18, 100.25),  # 13:40Z breakout: close 100.25 > 100.20
    11: (100.22, 100.30, 100.21, 100.28),  # 13:41Z entry bar (no same-bar exit)
    12: (100.28, 100.35, 100.26, 100.33),
    13: (100.33, 100.40, 100.30, 100.38),
    14: (100.38, 100.45, 100.35, 100.43),
    15: (100.43, 100.50, 100.40, 100.48),
    16: (100.48, 100.55, 100.45, 100.53),
    17: (100.53, 100.60, 100.50, 100.58),
    18: (100.58, 100.63, 100.55, 100.61),  # high 100.63 < config target ~100.64
    19: (100.61, 100.70, 100.58, 100.66),  # 13:49Z UNIQUE peak high 100.70
}


def gen_sample() -> dict:
    base = _open_utc("2025-05-15")  # 09:30 ET (EDT) -> 13:30Z
    bars = []
    for i in range(390):
        t = base + timedelta(minutes=i)
        if i in EXPLICIT:
            o, h, l, c = EXPLICIT[i]
        elif i <= 60:
            # Drift down from the 100.66 close to ~100.20; clamp so the 100.70
            # peak at i=19 stays unique and lows stay well above the 100.00 stop.
            frac = (i - 19) / (60 - 19)
            mid = 100.66 - frac * (100.66 - 100.20)
            o, c = mid + 0.01, mid - 0.01
            h, l = min(mid + 0.05, 100.69), max(mid - 0.05, 100.06)
        else:
            # Flat tail just above the stop; the final bar's close (100.15) is the
            # flatten reference for sweep points whose target is never reached.
            mid = 100.15
            o, c = mid + 0.02, mid
            h, l = mid + 0.06, mid - 0.05
        bars.append(_bar(t, o, h, l, c))

    _assert_valid(bars, expected=390)
    # invariants this fixture relies on
    highs_after_entry = [b["h"] for b in bars[12:]]
    assert max(highs_after_entry) == 100.70, max(highs_after_entry)
    assert sum(1 for b in bars[12:] if b["h"] == 100.70) == 1, "peak must be unique"
    assert min(b["l"] for b in bars[11:]) > 100.00, "stop must never be touched"
    assert bars[-1]["c"] == 100.15
    return {
        "symbol": "AAPL",
        "session_date": "2025-05-15",
        "timeframe": "1Min",
        "feed": "fixture",
        "is_half_day": False,
        "bars": bars,
    }


def gen_half_day() -> dict:
    base = _open_utc("2025-11-28")  # 09:30 ET (EST) -> 14:30Z, half day
    bars = []
    for i in range(210):  # 09:30 -> 13:00 ET = 210 minutes
        t = base + timedelta(minutes=i)
        mid = 100.0 + (i % 7) * 0.01  # gentle, deterministic, clean OHLC
        bars.append(_bar(t, mid, mid + 0.05, mid - 0.05, mid + 0.02))
    _assert_valid(bars, expected=210)
    return {
        "symbol": "AAPL",
        "session_date": "2025-11-28",
        "timeframe": "1Min",
        "feed": "fixture",
        "is_half_day": True,
        "bars": bars,
    }


def _assert_valid(bars, *, expected):
    assert len(bars) == expected, (len(bars), expected)
    for b in bars:
        assert b["l"] <= b["o"] <= b["h"], b
        assert b["l"] <= b["c"] <= b["h"], b
        assert b["l"] <= b["h"], b
        assert b["v"] > 0, b


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "sample_aapl_1m_day.json"), "w") as f:
        json.dump(gen_sample(), f, indent=2)
    with open(os.path.join(OUT, "half_day_aapl_1m.json"), "w") as f:
        json.dump(gen_half_day(), f, indent=2)
    print("wrote fixtures/sample_aapl_1m_day.json and fixtures/half_day_aapl_1m.json")


if __name__ == "__main__":
    main()
