"""Replay package: no-lookahead clock/view, the same-bar fill ban, and the
``run_replay`` orchestration (added in a later step)."""


class ReplayError(Exception):
    """Raised when the replay invariant is violated (e.g. a same-bar fill)."""


def enforce_no_same_bar_fill(*, signal_bar_ts, fill_bar_ts) -> None:
    """A signal on bar N must fill no earlier than bar N+1.

    ``signal_bar_ts == fill_bar_ts`` is structurally impossible in a correct
    replay; if it ever occurs we fail the run rather than report fantasy fills.
    """
    if signal_bar_ts == fill_bar_ts:
        raise ReplayError(f"same-bar fill detected: signal and fill both at {signal_bar_ts}")
