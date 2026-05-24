"""VWAP reclaim, long-only — a pre-registered hypothesis (not tuned).

Maintain the cumulative session VWAP from *completed* RTH bars only
(``Σ vwap_i·vol_i / Σ vol_i``; no lookahead). After a short warmup (the first 5 RTH
bars), trigger long when the bar that just completed closes **back above** the
cumulative VWAP having closed **below** it on the prior bar (a reclaim). The stop is
the lowest low since session open; the target is 1R from entry. One trade per day.

Fixed constants (pre-registered, deliberately not optimized): warmup = 5 RTH bars,
target = 1.0 R. Per-bar VWAP uses each bar's recorded ``vwap``, falling back to the
typical price ``(high+low+close)/3`` only when a bar has no ``vwap``.

NB: it only ever reads a ReplayView, so it is structurally incapable of lookahead.
"""

from ..models import TradePlan

_WARMUP_BARS = 5
_TARGET_R = 1.0

_MONITORING = "monitoring"
_DONE = "done"


def _bar_price(bar) -> float:
    return bar.vwap if bar.vwap is not None else (bar.high + bar.low + bar.close) / 3.0


def _cumulative_vwap(bars) -> float | None:
    total_vol = sum(b.volume for b in bars)
    if total_vol <= 0:
        return None
    return sum(_bar_price(b) * b.volume for b in bars) / total_vol


class VwapReclaimLongStrategy:
    def __init__(self, warmup_bars: int = _WARMUP_BARS, target_r_multiple: float = _TARGET_R):
        self.warmup_bars = int(warmup_bars)
        self.target_r_multiple = float(target_r_multiple)
        self.state = _MONITORING
        self._context: dict | None = None

    @classmethod
    def from_config(cls, config: dict) -> "VwapReclaimLongStrategy":
        return cls()

    def strategy_context(self) -> dict | None:
        return self._context

    def on_bar(self, view) -> TradePlan | None:
        if self.state == _DONE:
            return None

        rth = view.regular_market_bars()
        n = len(rth)
        # Need the signal bar to be strictly after the warmup window, plus a prior bar.
        if n < self.warmup_bars + 1:
            return None

        cur, prev = rth[-1], rth[-2]
        vwap_cur = _cumulative_vwap(rth)
        vwap_prev = _cumulative_vwap(rth[:-1])
        if vwap_cur is None or vwap_prev is None:
            return None

        reclaim = prev.close < vwap_prev and cur.close > vwap_cur
        if not reclaim:
            return None

        stop = min(b.low for b in rth)
        if not (stop < cur.close):   # long requires a stop strictly below the trigger
            return None

        self.state = _DONE
        self._context = {"cum_vwap": round(vwap_cur, 6)}
        return TradePlan(
            signal_bar_ts=cur.bar_start_ts,
            trigger_price=cur.close,
            stop_price=stop,
            target_r_multiple=self.target_r_multiple,
        )
