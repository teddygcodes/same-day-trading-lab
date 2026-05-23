"""Aggregate per-bar and session-level quality flags into a summary + validity verdict.

Fatal issues (mark a run INVALID_DATA): suspicious OHLC, missing bars beyond the
configured tolerance, duplicate bars, or a partial session (fewer RTH bars than the
half-day-aware expected grid). Non-fatal issues (flagged, not invalidating in v0.1):
zero volume, extreme single-bar moves, stale repeats, out-of-session bars.
"""

from . import flags


def evaluate(bars, session, config):
    """Return ``(per_bar_flags, summary, data_valid, reasons)``.

    ``per_bar_flags`` maps ``bar_start_ts`` -> tuple of flag names.
    """
    q = config["quality"]
    rth_bars = [b for b in bars if b.is_regular_market_hours]

    per_bar: dict = {b.bar_start_ts: [] for b in bars}
    suspicious = zero_vol = extreme = out_of_sess = 0
    for b in bars:
        if flags.flag_suspicious_ohlc(b):
            per_bar[b.bar_start_ts].append("suspicious_ohlc")
            suspicious += 1
        if flags.flag_zero_volume(b):
            per_bar[b.bar_start_ts].append("zero_volume")
            zero_vol += 1
        if flags.flag_out_of_session(b):
            per_bar[b.bar_start_ts].append("out_of_session")
            out_of_sess += 1
        if flags.flag_extreme_move(b, q["extreme_move_pct"]):
            per_bar[b.bar_start_ts].append("extreme_move")
            extreme += 1

    missing = flags.find_missing_bars(rth_bars, session)
    duplicates = flags.find_duplicate_bars(bars)
    for ts in duplicates:
        if ts in per_bar:
            per_bar[ts].append("duplicate_bar")
    stale_runs = flags.find_stale_repeats(bars, q["stale_repeat_min_consecutive"])
    for run in stale_runs:
        for ts in run:
            if ts in per_bar:
                per_bar[ts].append("stale_repeat")
    is_partial = flags.partial_session(len(rth_bars), session)

    summary = {
        "bar_count": len(bars),
        "rth_bar_count": len(rth_bars),
        "bar_count_expected": session.bar_count_expected,
        "missing_bar_count": len(missing),
        "missing_bars": [t.isoformat() for t in missing],
        "duplicate_bars": [t.isoformat() for t in duplicates],
        "stale_repeat_runs": [[t.isoformat() for t in run] for run in stale_runs],
        "partial_session": is_partial,
        "suspicious_ohlc_count": suspicious,
        "zero_volume_count": zero_vol,
        "extreme_move_count": extreme,
        "out_of_session_count": out_of_sess,
    }

    reasons = []
    if suspicious:
        reasons.append(f"{suspicious} suspicious OHLC bar(s)")
    if len(missing) > q["max_missing_bars"]:
        reasons.append(f"{len(missing)} missing bar(s) > max_missing_bars={q['max_missing_bars']}")
    if duplicates:
        reasons.append(f"{len(duplicates)} duplicate bar timestamp(s)")
    if is_partial:
        reasons.append(
            f"partial session: {len(rth_bars)} RTH bars < expected {session.bar_count_expected}"
        )
    data_valid = not reasons

    per_bar_flags = {ts: tuple(v) for ts, v in per_bar.items()}
    return per_bar_flags, summary, data_valid, reasons
