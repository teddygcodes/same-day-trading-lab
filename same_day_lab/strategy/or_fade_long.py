"""OR-fade (failed-breakdown reclaim), long-only — a pre-registered hypothesis (not tuned).

The opening range is the first N completed RTH bars (the Nth bar defines it and cannot
trigger). After the OR window, watch for a **breakdown**: a bar closes below the OR low.
Track the lowest low of that breakdown swing. When a **later bar closes back above the OR
low** (the bear-trap reclaim), go long: stop = the breakdown swing low (below the OR low),
target = 1R from entry. One trade per day.

This is the mirror of ORB's breakout *above* the OR high — here we fade a failed breakdown
*below* the OR low. Fixed constants (pre-registered, not optimized): target = 1.0 R; the OR
window follows ``opening_range_minutes`` from config (the same window ORB uses).

NB: it only ever reads a ReplayView, so it is structurally incapable of lookahead.
"""

from ..models import OpeningRange, TradePlan

_TARGET_R = 1.0

_WAITING_OR = "waiting_or"
_MONITORING = "monitoring"
_BROKE_DOWN = "broke_down"
_DONE = "done"


class OrFadeLongStrategy:
    def __init__(self, or_minutes: int = 5, target_r_multiple: float = _TARGET_R):
        self.or_minutes = int(or_minutes)
        self.target_r_multiple = float(target_r_multiple)
        self.state = _WAITING_OR
        self.opening_range: OpeningRange | None = None
        self._swing_low: float | None = None

    @classmethod
    def from_config(cls, config: dict) -> "OrFadeLongStrategy":
        orb = config["orb"]
        return cls(or_minutes=int(orb["opening_range_minutes"]))

    def strategy_context(self) -> dict | None:
        if self.opening_range is None:
            return None
        return {"or_high": self.opening_range.high, "or_low": self.opening_range.low}

    def on_bar(self, view) -> TradePlan | None:
        if self.state == _DONE:
            return None

        rth = view.regular_market_bars()
        n = len(rth)
        if n < self.or_minutes:
            return None

        if self.opening_range is None:
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

        bar = rth[-1]   # the bar just completed (strictly after the OR window)
        or_low = self.opening_range.low

        if self.state == _MONITORING:
            if bar.close < or_low:       # breakdown below the OR low
                self.state = _BROKE_DOWN
                self._swing_low = bar.low
            return None

        if self.state == _BROKE_DOWN:
            self._swing_low = min(self._swing_low, bar.low)
            if bar.close > or_low:       # reclaim back above the OR low -> bear trap
                stop = self._swing_low
                if not (stop < bar.close):
                    return None
                self.state = _DONE
                return TradePlan(
                    signal_bar_ts=bar.bar_start_ts,
                    trigger_price=bar.close,
                    stop_price=stop,
                    target_r_multiple=self.target_r_multiple,
                )
        return None
