"""Strategy registry — a minimal name→class map for the pre-registered strategies.

Each strategy is a class that:
  * builds from the full config via ``from_config(cls, config)`` (uniform construction);
  * implements ``on_bar(view) -> TradePlan | None`` reading **only** a ReplayView of
    completed bars (the no-lookahead firewall is structural, not disciplinary);
  * exposes ``strategy_context() -> dict | None`` (small context surfaced in the report,
    e.g. ORB's opening-range levels).

This is deliberately NOT a plugin framework: strategies are selected by name, nothing more.
"""

from .or_fade_long import OrFadeLongStrategy
from .orb_long import OrbLongStrategy
from .vwap_reclaim_long import VwapReclaimLongStrategy

DEFAULT_STRATEGY = "orb_long_5m"

STRATEGIES = {
    "orb_long_5m": OrbLongStrategy,
    "vwap_reclaim_long": VwapReclaimLongStrategy,
    "or_fade_long": OrFadeLongStrategy,
}


def get_strategy(name: str):
    """Resolve a registered strategy class by name, or raise on an unknown name."""
    try:
        return STRATEGIES[name]
    except KeyError:
        known = ", ".join(sorted(STRATEGIES))
        raise ValueError(f"unknown strategy {name!r}; known strategies: {known}") from None
