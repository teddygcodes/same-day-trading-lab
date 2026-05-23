"""Thin Alpaca historical 1-minute bars client (stdlib urllib, no framework).

Used only when ``--provider alpaca`` is requested AND creds are present. The live
HTTP path is intentionally not exercised by the offline test suite; everything it
emits flows through the same ``normalize`` layer the fixtures use.
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import timedelta

from .normalize import session_bounds

BASE_URL = "https://data.alpaca.markets/v2/stocks"


class AlpacaCredentialsMissing(RuntimeError):
    """Raised when an Alpaca run is requested without API credentials."""


def _creds() -> tuple[str, str]:
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise AlpacaCredentialsMissing(
            "No Alpaca creds (set ALPACA_API_KEY and ALPACA_SECRET_KEY); "
            "rerun with --provider fixture"
        )
    return key, secret


def fetch_bars(symbol: str, date: str, config: dict, *, feed: str = "iex") -> dict:
    """Fetch one RTH session of 1-minute bars, normalized into a fixture-shaped payload."""
    key, secret = _creds()
    bounds = session_bounds({"session_date": date, "is_half_day": False}, config)
    start = bounds["open"].isoformat()
    # +1 minute so the final bar (starting at the close-minus-one) is included.
    end = (bounds["close"] + timedelta(minutes=1)).isoformat()

    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    out_bars: list[dict] = []
    page_token = None
    while True:
        params = {"timeframe": "1Min", "start": start, "end": end, "feed": feed, "limit": 10000}
        if page_token:
            params["page_token"] = page_token
        url = f"{BASE_URL}/{urllib.parse.quote(symbol)}/bars?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (trusted host)
            data = json.loads(resp.read().decode("utf-8"))
        out_bars.extend(data.get("bars") or [])
        page_token = data.get("next_page_token")
        if not page_token:
            break

    return {
        "symbol": symbol,
        "session_date": date,
        "timeframe": "1Min",
        "feed": feed,
        "is_half_day": False,
        "bars": out_bars,
    }
