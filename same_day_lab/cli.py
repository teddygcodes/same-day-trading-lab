"""Command-line entry point.

Subcommands: init-db, ingest, run, reconstruct, report. This module only parses
arguments and dispatches to the pipeline modules.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from . import DATA_WARNING
from .config import config_hash, load_config
from .ingest import alpaca, fixture
from .ingest.normalize import build_session, normalize_bars
from .ingest.raw_archive import archive_raw
from .quality.summary import evaluate
from .storage import sqlite as db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raw_dir(db_path) -> str:
    """``raw`` subdirectory beside the SQLite file (defaults to project data/raw)."""
    base = db_path or db.DEFAULT_DB_PATH
    return os.path.join(os.path.dirname(os.path.abspath(base)), "raw")


def _bar_row(bar, ingest_run_id, flags, raw_hash, cfg_hash) -> dict:
    return {
        "ingest_run_id": ingest_run_id,
        "symbol": bar.symbol,
        "session_date": bar.session_date,
        "bar_start_ts_utc": bar.bar_start_ts.isoformat(),
        "bar_end_ts_utc": bar.bar_end_ts.isoformat(),
        "bar_duration_seconds": bar.bar_duration_seconds,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "vwap": bar.vwap,
        "trade_count": bar.trade_count,
        "provider": bar.provider,
        "feed": bar.feed,
        "is_regular_market_hours": int(bar.is_regular_market_hours),
        "quality_flags_json": json.dumps(list(flags)),
        "raw_hash": raw_hash,
        "config_hash": cfg_hash,
    }


def _cmd_init_db(args) -> int:
    conn = db.connect(args.db)
    db.init_db(conn)
    print(f"initialized schema at {args.db or db.DEFAULT_DB_PATH}")
    return 0


def _cmd_ingest(args) -> int:
    config = load_config()
    cfg_hash = config_hash(config)

    if args.provider == "alpaca":
        try:
            payload = alpaca.fetch_bars(args.symbol, args.date, config)
        except alpaca.AlpacaCredentialsMissing as exc:
            print(f"ingest failed: {exc}", file=sys.stderr)
            return 1
    else:
        payload = fixture.load_fixture(args.symbol, args.date)

    effective_date = payload["session_date"]
    archived = archive_raw(
        payload,
        provider=args.provider,
        symbol=args.symbol,
        date=effective_date,
        request_params={"symbol": args.symbol, "date": args.date, "provider": args.provider},
        config_hash=cfg_hash,
        raw_dir=_raw_dir(args.db),
    )

    bars = normalize_bars(payload, config, provider=args.provider)
    session = build_session(payload, bars, config)
    per_bar_flags, summary, data_valid, reasons = evaluate(bars, session, config)

    conn = db.connect(args.db)
    db.init_db(conn)
    db.insert_ingest_run(
        conn,
        {
            "ingest_run_id": archived["ingest_run_id"],
            "provider": args.provider,
            "symbol": args.symbol,
            "session_date": effective_date,
            "fetch_ts_utc": archived["fetch_ts_utc"],
            "raw_path": archived["path"],
            "raw_hash": archived["raw_hash"],
            "config_hash": cfg_hash,
            "source_warning": DATA_WARNING,
            "created_at_utc": _now(),
        },
    )
    db.delete_bars_for_ingest(conn, archived["ingest_run_id"])
    db.insert_bars(
        conn,
        [
            _bar_row(b, archived["ingest_run_id"], per_bar_flags.get(b.bar_start_ts, ()),
                     archived["raw_hash"], cfg_hash)
            for b in bars
        ],
    )
    db.upsert_session(
        conn,
        {
            "session_date": session.session_date,
            "symbol": session.symbol,
            "session_open_ts_utc": session.session_open_ts.isoformat(),
            "session_close_ts_utc": session.session_close_ts.isoformat(),
            "flatten_ts_utc": session.flatten_ts.isoformat(),
            "is_half_day": int(session.is_half_day),
            "bar_count_expected": session.bar_count_expected,
            "bar_count_actual": session.bar_count_actual,
            "quality_summary_json": json.dumps(summary),
            "config_hash": cfg_hash,
        },
    )

    print(f"ingested {len(bars)} bars for {args.symbol} {effective_date} (provider={args.provider})")
    print(f"  raw archived: {archived['path']}")
    print(f"  raw_hash: {archived['raw_hash'][:16]}...  config_hash: {cfg_hash[:16]}...")
    print(f"  bars expected/actual (RTH): {session.bar_count_expected}/{session.bar_count_actual}")
    print(f"  data_valid: {data_valid}" + (f"  reasons: {reasons}" if reasons else ""))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="same-day-lab", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="create the SQLite schema")
    p_init.add_argument("--db", default=None, help="path to the SQLite file")
    p_init.set_defaults(func=_cmd_init_db)

    p_ing = sub.add_parser("ingest", help="archive raw payload + write normalized bars")
    p_ing.add_argument("--provider", choices=["fixture", "alpaca"], default="fixture")
    p_ing.add_argument("--symbol", default="AAPL")
    p_ing.add_argument("--date", default="2025-05-15")
    p_ing.add_argument("--db", default=None, help="path to the SQLite file")
    p_ing.set_defaults(func=_cmd_ingest)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
