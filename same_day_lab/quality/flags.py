"""Pure bar-quality functions. No I/O, no DB — just (bar(s), params) -> result.

Kept pure so they are trivially unit-testable and reusable by the summary layer.
"""

from datetime import timedelta


def flag_suspicious_ohlc(bar) -> bool:
    """True if OHLC is internally inconsistent (high<low, or open/close outside range)."""
    if bar.high < bar.low:
        return True
    if not (bar.low <= bar.open <= bar.high):
        return True
    if not (bar.low <= bar.close <= bar.high):
        return True
    return False


def flag_zero_volume(bar) -> bool:
    return bar.volume == 0


def flag_out_of_session(bar) -> bool:
    """True if the bar is outside regular market hours (extended hours disallowed in v0.1)."""
    return not bar.is_regular_market_hours


def find_missing_bars(rth_bars, session) -> list:
    """Timestamps on the expected 60s grid (open -> close, close-exclusive) with no bar."""
    present = {b.bar_start_ts for b in rth_bars}
    missing = []
    t = session.session_open_ts
    while t < session.session_close_ts:
        if t not in present:
            missing.append(t)
        t = t + timedelta(seconds=60)
    return missing


def find_duplicate_bars(bars) -> list:
    """Start timestamps that appear more than once (returned once each)."""
    seen, dups, reported = set(), [], set()
    for b in bars:
        ts = b.bar_start_ts
        if ts in seen and ts not in reported:
            dups.append(ts)
            reported.add(ts)
        seen.add(ts)
    return dups


def find_stale_repeats(bars, min_consecutive: int) -> list:
    """Runs of >= N consecutive bars with identical (o,h,l,c,v). Returns lists of timestamps."""
    runs = []
    run = []
    prev_key = None
    for b in bars:
        key = (b.open, b.high, b.low, b.close, b.volume)
        if key == prev_key:
            run.append(b.bar_start_ts)
        else:
            if len(run) >= min_consecutive:
                runs.append(run)
            run = [b.bar_start_ts]
            prev_key = key
    if len(run) >= min_consecutive:
        runs.append(run)
    return runs


def flag_extreme_move(bar, pct: float) -> bool:
    """True if the intrabar range exceeds ``pct`` percent of the bar's open."""
    if bar.open <= 0:
        return False
    return (bar.high - bar.low) / bar.open * 100.0 > pct


def _consecutive_runs(missing, *, step_seconds=60) -> list:
    """Group an ascending list of missing timestamps into maximal consecutive runs."""
    runs = []
    for ts in missing:
        if runs and ts - runs[-1][-1] == timedelta(seconds=step_seconds):
            runs[-1].append(ts)
        else:
            runs.append([ts])
    return runs


def _touches_edge(run, session, *, step_seconds=60) -> bool:
    last_slot = session.session_close_ts - timedelta(seconds=step_seconds)
    return run[0] == session.session_open_ts or run[-1] == last_slot


def find_halt_runs(missing, session, min_consecutive: int, *, step_seconds=60) -> list:
    """Interior consecutive-missing runs of >= min_consecutive minutes (non-fatal halts).

    A run anchored at the session open or final grid slot is truncation (see
    ``partial_session``), not a halt, so it is excluded here.
    """
    return [
        run
        for run in _consecutive_runs(missing, step_seconds=step_seconds)
        if len(run) >= min_consecutive and not _touches_edge(run, session, step_seconds=step_seconds)
    ]


def partial_session(missing, session, min_consecutive: int, *, step_seconds=60) -> bool:
    """True if a leading or trailing missing run >= min_consecutive reaches a session
    edge — the feed never covered the full session (truncation). Interior gaps do not."""
    return any(
        len(run) >= min_consecutive and _touches_edge(run, session, step_seconds=step_seconds)
        for run in _consecutive_runs(missing, step_seconds=step_seconds)
    )
