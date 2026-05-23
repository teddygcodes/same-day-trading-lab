"""Thin Alpaca historical 1-minute bars client (stdlib urllib, no framework).

Used only when ``--provider alpaca`` is requested AND creds are present. The live
HTTP path is intentionally not exercised by the offline test suite; everything it
emits flows through the same ``normalize`` layer the fixtures use. Errors are mapped
to clear, graceful messages (no tracebacks) via ``AlpacaError``.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from .normalize import session_bounds

BASE_URL = "https://data.alpaca.markets/v2/stocks"


class AlpacaCredentialsMissing(RuntimeError):
    """Raised when an Alpaca run is requested without API credentials."""


class AlpacaError(RuntimeError):
    """User-facing Alpaca failure (mapped from HTTP/network errors); no tracebacks."""


def _creds() -> tuple[str, str]:
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise AlpacaCredentialsMissing(
            "No Alpaca creds (set ALPACA_API_KEY and ALPACA_SECRET_KEY); "
            "rerun with --provider fixture"
        )
    return key, secret


def _retry_after_seconds(err, default=1.0) -> float:
    raw = err.headers.get("Retry-After") if getattr(err, "headers", None) else None
    try:
        return float(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


def _get_json(url: str, headers: dict, *, _retried: bool = False) -> dict:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (trusted host)
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AlpacaError(
                f"Alpaca rejected the credentials (HTTP {e.code}); "
                "check ALPACA_API_KEY / ALPACA_SECRET_KEY"
            ) from None
        if e.code == 429 and not _retried:
            time.sleep(_retry_after_seconds(e))
            return _get_json(url, headers, _retried=True)
        if e.code == 429:
            raise AlpacaError("Alpaca rate limited (HTTP 429) after one retry; try again later") from None
        raise AlpacaError(f"Alpaca HTTP {e.code}: {e.reason}") from None
    except urllib.error.URLError as e:
        raise AlpacaError(f"network error reaching Alpaca: {e.reason}") from None


def fetch_bars(symbol: str, date: str, config: dict, *, feed: str = "iex") -> dict:
    """Fetch one RTH session of 1-minute IEX bars, normalized into a fixture-shaped payload."""
    key, secret = _creds()
    bounds = session_bounds({"session_date": date, "is_half_day": False}, config)
    start = bounds["open"].isoformat()
    # +1 minute so the final bar (starting at the close-minus-one) is included.
    end = (bounds["close"] + timedelta(minutes=1)).isoformat()
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}

    out_bars: list[dict] = []
    page_token = None
    while True:
        params = {
            "timeframe": "1Min", "start": start, "end": end,
            "feed": feed, "adjustment": "raw", "limit": 10000,
        }
        if page_token:
            params["page_token"] = page_token
        url = f"{BASE_URL}/{urllib.parse.quote(symbol)}/bars?{urllib.parse.urlencode(params)}"
        data = _get_json(url, headers)
        out_bars.extend(data.get("bars") or [])
        page_token = data.get("next_page_token")
        if not page_token:
            break

    if not out_bars:
        raise AlpacaError("no bars returned (non-trading day or bad symbol/date)")

    return {
        "symbol": symbol,
        "session_date": date,
        "timeframe": "1Min",
        "feed": feed,
        "is_half_day": False,
        "bars": out_bars,
    }
