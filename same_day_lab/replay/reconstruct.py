"""Reconstruct "what the system knew at time T".

The ``--time`` argument is a wall-clock time in the configured market timezone
(America/New_York) on the session date; it is converted to UTC for bar lookup.
Reconstruction replays the archived raw payload up to that instant and verifies the
stored raw hash still matches the archived bytes.
"""

import json

from ..hashing import content_hash
from ..ingest.normalize import market_time_to_utc, normalize_bars
from ..storage import sqlite as db
from .clock import ReplayClock


def reconstruct(symbol: str, date: str, time_str: str, config: dict, conn) -> dict:
    row = db.get_ingest_run(conn, symbol, date)
    if row is None:
        raise LookupError(f"no ingest found for {symbol} {date}; run `ingest` first")

    with open(row["raw_path"]) as f:
        archived = json.load(f)
    raw_payload = archived["raw_payload"]
    recomputed = content_hash(raw_payload)
    raw_hash_ok = recomputed == row["raw_hash"]

    target_utc = market_time_to_utc(date, time_str, config)
    bars = normalize_bars(raw_payload, config, provider=row["provider"])

    clock = ReplayClock(bars)
    completed = 0
    last = None
    while not clock.is_done():
        nxt = clock.advance()
        if nxt.bar_start_ts > target_utc:
            break
        completed += 1
        last = nxt

    return {
        "symbol": symbol,
        "session_date": date,
        "provider": row["provider"],
        "fetch_ts_utc": row["fetch_ts_utc"],
        "as_of_market_time": f"{time_str} {config['market_timezone']}",
        "as_of_utc": target_utc.isoformat(),
        "completed_bar_count": completed,
        "last_bar": (
            {
                "bar_start_ts_utc": last.bar_start_ts.isoformat(),
                "open": last.open,
                "high": last.high,
                "low": last.low,
                "close": last.close,
                "volume": last.volume,
            }
            if last is not None
            else None
        ),
        "raw_hash": row["raw_hash"],
        "raw_hash_verified": raw_hash_ok,
    }
