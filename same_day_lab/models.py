"""Internal bar/session/trade models.

Provider payloads are normalized into these so a second provider could be added
later without touching downstream code. All datetimes are timezone-aware UTC.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Bar:
    symbol: str
    session_date: str
    bar_start_ts: datetime          # UTC, bar open instant
    bar_end_ts: datetime            # UTC, start + duration
    bar_duration_seconds: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    provider: str
    is_regular_market_hours: bool
    vwap: float | None = None
    trade_count: int | None = None
    feed: str | None = None
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Session:
    session_date: str
    symbol: str
    session_open_ts: datetime
    session_close_ts: datetime
    flatten_ts: datetime
    is_half_day: bool
    bar_count_expected: int
    bar_count_actual: int


@dataclass(frozen=True)
class OpeningRange:
    high: float
    low: float
    start_ts: datetime
    end_ts: datetime
    bar_count: int


@dataclass(frozen=True)
class EntrySignal:
    signal_bar_ts: datetime
    trigger_price: float


@dataclass(frozen=True)
class FillParams:
    entry_cents: float
    exit_cents: float
    entry_bps: float
    exit_bps: float


@dataclass(frozen=True)
class CanonicalTrade:
    """One ORB trade priced two ways on a single (pessimistic) path.

    The pessimistic simulation defines the path (entry bar, exit bar, reason);
    naive re-prices that same path at zero slippage, which structurally yields
    ``naive_pnl >= pessimistic_pnl``.
    """

    or_high: float
    or_low: float
    signal_bar_ts: datetime
    fill_bar_ts: datetime
    exit_signal_bar_ts: datetime | None
    exit_fill_bar_ts: datetime | None
    trigger_price: float
    naive_entry_price: float
    naive_exit_price: float
    naive_pnl: float
    pessimistic_entry_price: float
    pessimistic_exit_price: float
    pessimistic_pnl: float
    exit_reason: str                # "target" | "stop" | "flatten"
    friction_sweep: list
    notes: dict = field(default_factory=dict)
