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


def gen_messy() -> dict:
    """Full RTH day resembling real IEX data: scattered missing minutes, one
    interior halt-like run (>= halt threshold), an extreme-move bar, and a
    zero-volume bar. Deterministic, OHLC-valid, and still produces the ORB trade."""
    base = _open_utc("2025-06-16")              # Mon, EDT -> 13:30Z .. 20:00Z (390-min grid)
    drop = set(range(200, 212)) | {75, 150, 250, 330}     # 12-min interior halt + 4 scattered = 16
    overrides = {                                # (o, h, l, c, v) for special bars
        # Extreme-move bar in the PRE-breakout lull: close (100.19) stays below the
        # OR high (100.20) so it does NOT signal, and being pre-signal it is absent
        # from bars_after_signal — so the friction sweep's re-simulation can never
        # mistake its 106 spike for a target hit. It still trips the extreme_move flag.
        7: (100.18, 106.00, 100.14, 100.19, 5000),        # extreme move (range ~5.9% > 5%, non-fatal)
        180: (100.15, 100.16, 100.14, 100.15, 0),         # zero volume (non-fatal)
    }
    assert 0 not in drop and 389 not in drop, "open/close edges must stay covered"
    # Guard: any extreme-move override must stay pre-signal (index < breakout at i=10).
    assert all(i < 10 for i, (o, h, l, c, v) in overrides.items() if (h - l) / o * 100.0 > 5.0)

    bars = []
    for i in range(390):
        if i in drop:
            continue
        t = base + timedelta(minutes=i)
        if i in overrides:
            o, h, l, c, v = overrides[i]
            bars.append(_bar(t, o, h, l, c, v=v))
            continue
        if i in EXPLICIT:
            o, h, l, c = EXPLICIT[i]
        elif i <= 60:
            frac = (i - 19) / (60 - 19)
            mid = 100.66 - frac * (100.66 - 100.20)
            o, c = mid + 0.01, mid - 0.01
            h, l = min(mid + 0.05, 100.69), max(mid - 0.05, 100.06)
        else:
            mid = 100.15
            o, c = mid + 0.02, mid
            h, l = mid + 0.06, mid - 0.05
        bars.append(_bar(t, o, h, l, c))

    # invariants the messy fixture relies on
    for b in bars:
        assert b["l"] <= b["o"] <= b["h"], b
        assert b["l"] <= b["c"] <= b["h"], b
        assert b["l"] <= b["h"], b
        assert b["v"] >= 0, b
    assert sum(1 for b in bars if b["v"] == 0) == 1, "exactly one zero-volume bar"
    assert len(bars) == 390 - len(drop)          # = 374; no fabrication, gaps stay gaps
    return {
        "symbol": "AAPL",
        "session_date": "2025-06-16",
        "timeframe": "1Min",
        "feed": "fixture",
        "is_half_day": False,
        "bars": bars,
    }


# ---- v0.3 multi-day synthetic mix (2025-07-07 Mon .. 07-10 Thu) -------------
# Same OR (high 100.20, low 100.00) and pre-breakout lull as the sample; the four
# days diverge only after the breakout so the verdict differences are isolated to
# the post-entry path. 07-11 (Fri) is deliberately left ungenerated → the
# missing-weekday case for run-range.

_OR_LULL = {
    0: (100.05, 100.15, 100.00, 100.10),
    1: (100.10, 100.20, 100.05, 100.15),
    2: (100.15, 100.18, 100.08, 100.12),
    3: (100.12, 100.19, 100.05, 100.14),
    4: (100.14, 100.20, 100.02, 100.16),  # OR high 100.20, OR low 100.00
    5: (100.16, 100.20, 100.12, 100.18),  # lull: closes never exceed the OR high
    6: (100.18, 100.20, 100.14, 100.19),
    7: (100.19, 100.20, 100.13, 100.17),
    8: (100.17, 100.20, 100.12, 100.18),
    9: (100.18, 100.20, 100.15, 100.19),
}

# Survive-friction day: a large breakout that runs to ~102, so the target is hit at
# every sweep point (with r=1 and stop=OR-low, cents-slippage nearly cancels), the
# pass-threshold P&L stays positive -> PASS_FOR_MORE_TESTING.
_SURVIVE = {
    **_OR_LULL,
    10: (100.19, 100.30, 100.18, 100.25),  # breakout close 100.25 > 100.20
    11: (100.30, 100.45, 100.28, 100.42),  # entry bar (open 100.30)
    12: (100.42, 100.55, 100.40, 100.52),
    13: (100.52, 100.70, 100.50, 100.68),
    14: (100.68, 101.05, 100.66, 101.02),  # clears the 5c target -> target hit
    15: (101.02, 101.45, 101.00, 101.42),
    16: (101.42, 101.85, 101.40, 101.82),
    17: (101.82, 102.05, 101.80, 102.00),  # peak ~102
}

# KILL day: a fizzled breakout. The day ends slightly above the breakout close, so
# naive (zero-slippage, entry at the trigger close) shows a small win — but the
# pessimistic entry sits above it after slippage and the target is never reached, so
# the trade flattens underwater -> naive>0 while pessimistic_default<=0 = KILL.
_KILL = {
    **_OR_LULL,
    10: (100.19, 100.28, 100.18, 100.25),  # breakout close 100.25
    11: (100.22, 100.32, 100.20, 100.28),  # entry bar (open 100.22 -> entry_ref stays 100.25)
}


def gen_survive() -> dict:
    base = _open_utc("2025-07-07")
    bars = []
    for i in range(390):
        t = base + timedelta(minutes=i)
        if i in _SURVIVE:
            o, h, l, c = _SURVIVE[i]
        else:  # flat tail well above the stop; the trade already exited at the target
            mid = 101.90 + (i % 5) * 0.01
            o, h, l, c = mid, mid + 0.05, mid - 0.05, mid + 0.02
        bars.append(_bar(t, o, h, l, c))
    _assert_valid(bars, expected=390)
    assert min(b["l"] for b in bars[11:]) > 100.00, "stop must never be touched"
    return {"symbol": "AAPL", "session_date": "2025-07-07", "timeframe": "1Min",
            "feed": "fixture", "is_half_day": False, "bars": bars}


def gen_kill() -> dict:
    base = _open_utc("2025-07-08")
    bars = []
    for i in range(390):
        t = base + timedelta(minutes=i)
        if i in _KILL:
            o, h, l, c = _KILL[i]
        elif i == 389:  # flatten bar (15:59): close above the breakout -> naive wins
            o, h, l, c = (100.31, 100.35, 100.27, 100.30)
        else:  # range-bound below the target, above the stop: hits neither
            mid = 100.30 + (i % 5) * 0.02
            o, h, l, c = mid, mid + 0.04, mid - 0.05, mid
        bars.append(_bar(t, o, h, l, c))
    _assert_valid(bars, expected=390)
    post = bars[12:]  # strictly after the entry bar
    assert max(b["h"] for b in post) < 100.64, "target must stay out of reach at default friction"
    assert min(b["l"] for b in post) > 100.00, "stop must never be touched"
    assert bars[389]["c"] == 100.30, "flatten close above the breakout so naive shows a win"
    return {"symbol": "AAPL", "session_date": "2025-07-08", "timeframe": "1Min",
            "feed": "fixture", "is_half_day": False, "bars": bars}


def gen_no_signal() -> dict:
    base = _open_utc("2025-07-09")
    bars = []
    for i in range(390):
        t = base + timedelta(minutes=i)
        if i in _OR_LULL:
            o, h, l, c = _OR_LULL[i]
        else:  # range-bound below the OR high forever -> no breakout close, no trade
            mid = 100.08 + (i % 7) * 0.01
            o, h, l, c = mid, mid + 0.04, mid - 0.04, mid + 0.02
        bars.append(_bar(t, o, h, l, c))
    _assert_valid(bars, expected=390)
    assert max(b["c"] for b in bars) <= 100.20, "no close may exceed the OR high"
    return {"symbol": "AAPL", "session_date": "2025-07-09", "timeframe": "1Min",
            "feed": "fixture", "is_half_day": False, "bars": bars}


def gen_invalid() -> dict:
    """A leading 40-minute gap reaching the session-open edge: the feed never
    covered the full session -> partial session -> INVALID_DATA. Flat, no breakout,
    so no trade is conflated with the invalid-data verdict."""
    base = _open_utc("2025-07-10")
    bars = []
    for i in range(40, 390):  # omit the first 40 RTH minutes (no fabrication; gap stays a gap)
        t = base + timedelta(minutes=i)
        mid = 100.05 + (i % 3) * 0.01
        o, h, l, c = mid, mid + 0.03, mid - 0.03, mid + 0.01
        bars.append(_bar(t, o, h, l, c))
    for b in bars:
        assert b["l"] <= b["o"] <= b["h"] and b["l"] <= b["c"] <= b["h"] and b["v"] > 0, b
    assert len(bars) == 350, len(bars)  # intentionally < 390; the missing run is the point
    return {"symbol": "AAPL", "session_date": "2025-07-10", "timeframe": "1Min",
            "feed": "fixture", "is_half_day": False, "bars": bars}


# ---- v0.4b two-window tournament mix ----------------------------------------
# A decide window (2025-08-04 Mon .. 08-08 Fri; ingest 08-04, 08-05) and a holdout
# window (2025-08-11 Mon .. 08-15 Fri; ingest 08-11, 08-12), engineered so the three
# registered strategies show a spread under the tournament's "survives a window" rule:
#   orb_long_5m       — survives decide (an orb-survive day), but a holdout KILL day
#                       drops it: the holdout gate visibly bites (carried_forward False).
#   or_fade_long      — survives BOTH windows (an or-fade-survive day in each):
#                       carried_forward True.
#   vwap_reclaim_long — never triggers on any of these days: no-signal everywhere.
# The remaining weekdays in each window are left ungenerated → per-window missing-weekday
# surfacing. Days reuse the shared _OR_LULL (OR high 100.20, OR low 100.00); they diverge
# only after the OR so the strategy differences are isolated.

# OR-fade survive shape: a breakdown below the OR low, a reclaim back above it (the
# or_fade long signal), then a single high spike that exceeds the target — while every
# CLOSE stays below the OR high (so orb never triggers) and below the rising cumulative
# VWAP (so vwap never reclaims). Only or_fade trades; it hits its target.
_ORFADE = {
    **_OR_LULL,
    10: (100.10, 100.12, 99.40, 99.99),    # breakdown: close 99.99 < OR low; deep low 99.40 = swing low (wide stop)
    11: (99.99, 100.06, 99.95, 100.05),    # reclaim: close 100.05 > OR low -> or_fade signal (still below cum VWAP)
    12: (100.00, 100.10, 99.95, 100.02),   # entry bar (exits only scan strictly after this)
    13: (100.02, 101.20, 100.00, 100.05),  # target spike: high 101.20 >> target; close stays low (orb & vwap silent)
}


def _gen_orb_survive_day(date_str: str) -> dict:
    base = _open_utc(date_str)
    bars = []
    for i in range(390):
        t = base + timedelta(minutes=i)
        if i in _SURVIVE:
            o, h, l, c = _SURVIVE[i]
        else:  # flat tail well above the stop; the trade already exited at the target
            mid = 101.90 + (i % 5) * 0.01
            o, h, l, c = mid, mid + 0.05, mid - 0.05, mid + 0.02
        bars.append(_bar(t, o, h, l, c))
    _assert_valid(bars, expected=390)
    assert min(b["l"] for b in bars[11:]) > 100.00, "stop must never be touched; no OR-low breakdown"
    return {"symbol": "AAPL", "session_date": date_str, "timeframe": "1Min",
            "feed": "fixture", "is_half_day": False, "bars": bars}


def _gen_orb_kill_day(date_str: str) -> dict:
    base = _open_utc(date_str)
    bars = []
    for i in range(390):
        t = base + timedelta(minutes=i)
        if i in _KILL:
            o, h, l, c = _KILL[i]
        elif i == 389:  # flatten bar: close above the breakout -> naive shows a win
            o, h, l, c = (100.31, 100.35, 100.27, 100.30)
        else:  # range-bound below the target, above the stop and OR low: hits neither
            mid = 100.30 + (i % 5) * 0.02
            o, h, l, c = mid, mid + 0.04, mid - 0.05, mid
        bars.append(_bar(t, o, h, l, c))
    _assert_valid(bars, expected=390)
    post = bars[12:]
    assert max(b["h"] for b in post) < 100.64, "target must stay out of reach at default friction"
    assert min(b["l"] for b in bars[10:]) > 100.00, "no OR-low breakdown -> or_fade stays silent"
    assert bars[389]["c"] == 100.30
    return {"symbol": "AAPL", "session_date": date_str, "timeframe": "1Min",
            "feed": "fixture", "is_half_day": False, "bars": bars}


def _gen_or_fade_survive_day(date_str: str) -> dict:
    base = _open_utc(date_str)
    bars = []
    for i in range(390):
        t = base + timedelta(minutes=i)
        if i in _ORFADE:
            o, h, l, c = _ORFADE[i]
        else:  # flat low tail: closes below the OR high AND below cum VWAP -> orb & vwap silent
            mid = 100.00
            o, h, l, c = mid, mid + 0.04, mid - 0.04, mid
        bars.append(_bar(t, o, h, l, c))
    _assert_valid(bars, expected=390)
    assert max(b["c"] for b in bars) <= 100.20, "no close above the OR high -> orb never triggers"
    assert min(b["l"] for b in bars) == 99.40, "swing low for the or_fade stop"
    return {"symbol": "AAPL", "session_date": date_str, "timeframe": "1Min",
            "feed": "fixture", "is_half_day": False, "bars": bars}


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
    with open(os.path.join(OUT, "messy_real_aapl_1m.json"), "w") as f:
        json.dump(gen_messy(), f, indent=2)
    # v0.3 multi-day mix
    for fn, gen in (
        ("survive_aapl_1m.json", gen_survive),
        ("kill_aapl_1m.json", gen_kill),
        ("nosignal_aapl_1m.json", gen_no_signal),
        ("invalid_aapl_1m.json", gen_invalid),
    ):
        with open(os.path.join(OUT, fn), "w") as f:
            json.dump(gen(), f, indent=2)
    # v0.4b two-window tournament mix
    for fn, gen, date_str in (
        ("orb_survive_0804_aapl_1m.json", _gen_orb_survive_day, "2025-08-04"),
        ("or_fade_survive_0805_aapl_1m.json", _gen_or_fade_survive_day, "2025-08-05"),
        ("orb_kill_0811_aapl_1m.json", _gen_orb_kill_day, "2025-08-11"),
        ("or_fade_survive_0812_aapl_1m.json", _gen_or_fade_survive_day, "2025-08-12"),
    ):
        with open(os.path.join(OUT, fn), "w") as f:
            json.dump(gen(date_str), f, indent=2)
    print("wrote fixtures/sample_aapl_1m_day.json and fixtures/half_day_aapl_1m.json")
    print("wrote fixtures/messy_real_aapl_1m.json")
    print("wrote fixtures/{survive,kill,nosignal,invalid}_aapl_1m.json")
    print("wrote fixtures/{orb_survive_0804,or_fade_survive_0805,orb_kill_0811,or_fade_survive_0812}_aapl_1m.json")


if __name__ == "__main__":
    main()
