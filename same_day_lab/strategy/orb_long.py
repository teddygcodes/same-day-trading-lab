"""5-minute opening-range-breakout, long-only — the v0.1 smoke-test strategy.

This emits an EntrySignal only; it never computes fills (the engine does). The
opening range is the first N completed regular-market bars; the Nth bar defines
the range and can NOT itself trigger (breakout monitoring starts on bar N+1).
Trigger rule is ``close_above_or_high`` (a close strictly above the OR high), not
a high-of-bar break. One trade per day.

NB: it only ever reads a ReplayView, so it is structurally incapable of lookahead.
"""

from ..models import EntrySignal, OpeningRange

_WAITING = "waiting_or"
_MONITORING = "monitoring"
_DONE = "done"


class OrbLongStrategy:
    def __init__(self, orb_config: dict):
        self.or_minutes = int(orb_config["opening_range_minutes"])
        self.state = _WAITING
        self.opening_range: OpeningRange | None = None

    def on_bar(self, view) -> EntrySignal | None:
        rth = view.regular_market_bars()
        n = len(rth)

        if n < self.or_minutes:
            return None

        if self.opening_range is None:
            # The bar that just completed is the Nth OR bar: it defines the range
            # and must not trigger. (In a per-bar replay, n == or_minutes here.)
            window = rth[: self.or_minutes]
            self.opening_range = OpeningRange(
                high=max(b.high for b in window),
                low=min(b.low for b in window),
                start_ts=window[0].bar_start_ts,
                end_ts=window[-1].bar_end_ts,
                bar_count=self.or_minutes,
            )
            self.state = _MONITORING
            return None

        if self.state != _MONITORING:
            return None

        bar = rth[-1]   # the bar just completed (strictly after the OR window)
        if bar.close > self.opening_range.high:
            self.state = _DONE
            return EntrySignal(signal_bar_ts=bar.bar_start_ts, trigger_price=bar.close)
        return None
