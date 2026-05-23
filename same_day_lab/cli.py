"""Command-line entry point.

Subcommands: init-db, ingest, run, reconstruct, report. This module only parses
arguments and dispatches to the pipeline modules.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

from . import DATA_WARNING
from .config import config_hash, load_config
from .fills.sweep import pnl_at
from .hashing import content_hash
from .ingest import alpaca, fixture
from .ingest.normalize import build_session, normalize_bars
from .ingest.raw_archive import archive_raw
from .quality.summary import evaluate
from .replay import run_replay
from .replay.reconstruct import reconstruct
from .reports.verdict import decide_verdict
from .reports.writer import STRATEGY_NAME, build_report, write_reports
from .storage import sqlite as db

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raw_dir(db_path) -> str:
    """``raw`` subdirectory beside the SQLite file (defaults to project data/raw)."""
    base = db_path or db.DEFAULT_DB_PATH
    return os.path.join(os.path.dirname(os.path.abspath(base)), "raw")


def _reports_dir(db_path) -> str:
    """Project ``reports/`` for the default DB, else a ``reports`` dir beside a custom DB."""
    if db_path is None:
        return os.path.join(PROJECT_ROOT, "reports")
    return os.path.join(os.path.dirname(os.path.abspath(db_path)), "reports")


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
        except (alpaca.AlpacaCredentialsMissing, alpaca.AlpacaError) as exc:
            print(f"ingest failed: {exc}", file=sys.stderr)
            return 1
    else:
        try:
            payload = fixture.load_fixture(args.symbol, args.date)
        except fixture.FixtureNotFound as exc:
            print(f"ingest failed: {exc}", file=sys.stderr)
            return 1

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


def _cmd_run(args) -> int:
    config = load_config()
    cfg_hash = config_hash(config)
    conn = db.connect(args.db)
    db.init_db(conn)

    ing = db.get_ingest_run(conn, args.symbol, args.date)
    if ing is None:
        print(
            f"run failed: no ingest for {args.symbol} {args.date}; run `ingest` first",
            file=sys.stderr,
        )
        return 1

    with open(ing["raw_path"]) as f:
        payload = json.load(f)["raw_payload"]
    bars = normalize_bars(payload, config, provider=ing["provider"])
    session = build_session(payload, bars, config)
    _per_bar, summary, data_valid, reasons = evaluate(bars, session, config)
    rth = [b for b in bars if b.is_regular_market_hours]

    started = _now()
    rr = run_replay(rth, config, flatten_ts=session.flatten_ts)
    trade = rr["trade"]

    if trade is not None:
        pess_default = trade.pessimistic_pnl
        ex_bps = config["fills"]["pessimistic"]["exit_slippage_bps"]
        pass_cents = config["verdict"]["min_friction_cents_to_pass"]
        pess_pass = pnl_at(trade.friction_sweep, cents=pass_cents, bps=ex_bps)
        naive_pnl = trade.naive_pnl
    else:
        pess_default = pess_pass = naive_pnl = None

    verdict = decide_verdict(
        replay_valid=rr["replay_valid"],
        data_valid=data_valid,
        signal_present=trade is not None,
        naive_pnl=naive_pnl,
        pessimistic_default_pnl=pess_default,
        pessimistic_pass_pnl=pess_pass,
        config=config,
    )

    run_id = f"run_{args.symbol}_{session.session_date}_{uuid.uuid4().hex[:8]}"
    completed = _now()
    report = build_report(
        run_id=run_id,
        symbol=args.symbol,
        session_date=session.session_date,
        provider=ing["provider"],
        feed=payload.get("feed"),
        config_hash=cfg_hash,
        ingest_run_id=ing["ingest_run_id"],
        raw_hash=ing["raw_hash"],
        quality_summary=summary,
        bar_count_expected=session.bar_count_expected,
        bar_count_actual=session.bar_count_actual,
        replay_result=rr,
        data_valid=data_valid,
        data_reasons=reasons,
        verdict=verdict,
        pessimistic_default_pnl=pess_default,
        pessimistic_pass_pnl=pess_pass,
        started_at=started,
        completed_at=completed,
    )
    json_path, md_path = write_reports(report, _reports_dir(args.db))

    db.insert_run(
        conn,
        {
            "run_id": run_id,
            "ingest_run_id": ing["ingest_run_id"],
            "symbol": args.symbol,
            "session_date": session.session_date,
            "strategy_name": STRATEGY_NAME,
            "strategy_config_hash": content_hash(config["orb"]),
            "config_hash": cfg_hash,
            "started_at_utc": started,
            "completed_at_utc": completed,
            "report_json_path": json_path,
            "report_md_path": md_path,
            "report_hash": report["report_hash"],
            "verdict": verdict,
        },
    )
    if trade is not None:
        db.insert_trade(
            conn,
            {
                "trade_id": f"{run_id}_t1",
                "run_id": run_id,
                "symbol": args.symbol,
                "session_date": session.session_date,
                "signal_bar_ts_utc": trade.signal_bar_ts.isoformat(),
                "fill_bar_ts_utc": trade.fill_bar_ts.isoformat(),
                "exit_signal_bar_ts_utc": trade.exit_signal_bar_ts.isoformat(),
                "exit_fill_bar_ts_utc": trade.exit_fill_bar_ts.isoformat(),
                "opening_range_high": trade.or_high,
                "opening_range_low": trade.or_low,
                "trigger_price": trade.trigger_price,
                "naive_entry_price": trade.naive_entry_price,
                "naive_exit_price": trade.naive_exit_price,
                "naive_pnl": trade.naive_pnl,
                "pessimistic_entry_price": trade.pessimistic_entry_price,
                "pessimistic_exit_price": trade.pessimistic_exit_price,
                "pessimistic_pnl": trade.pessimistic_pnl,
                "friction_sweep_json": json.dumps(trade.friction_sweep),
                "exit_reason": trade.exit_reason,
                "notes_json": json.dumps(trade.notes),
            },
        )

    print(f"verdict: {verdict}")
    print(f"  report json: {json_path}")
    print(f"  report md:   {md_path}")
    print(f"  report_hash: {report['report_hash'][:16]}...")
    return 0


def _cmd_reconstruct(args) -> int:
    config = load_config()
    conn = db.connect(args.db)
    try:
        result = reconstruct(args.symbol, args.date, args.time, config, conn)
    except LookupError as exc:
        print(f"reconstruct failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_report(args) -> int:
    conn = db.connect(args.db)
    row = db.latest_run(conn, args.symbol, args.date)
    if row is None:
        print(
            f"no run found for {args.symbol} {args.date}; run `run` first", file=sys.stderr
        )
        return 1
    print(f"latest run: {row['run_id']}  verdict={row['verdict']}")
    print(f"  json: {row['report_json_path']}")
    print(f"  md:   {row['report_md_path']}")
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

    p_run = sub.add_parser("run", help="replay + ORB + dual fills + report")
    p_run.add_argument("--symbol", default="AAPL")
    p_run.add_argument("--date", default="2025-05-15")
    p_run.add_argument("--db", default=None, help="path to the SQLite file")
    p_run.set_defaults(func=_cmd_run)

    p_rec = sub.add_parser(
        "reconstruct",
        help="show replay state at a market-timezone instant",
        description="--time is interpreted in the configured market_timezone "
        "(America/New_York) on --date, then converted to UTC for bar lookup.",
    )
    p_rec.add_argument("--symbol", default="AAPL")
    p_rec.add_argument("--date", default="2025-05-15")
    p_rec.add_argument(
        "--time", required=True, help='market-timezone wall clock, e.g. "10:32" (America/New_York)'
    )
    p_rec.add_argument("--db", default=None, help="path to the SQLite file")
    p_rec.set_defaults(func=_cmd_reconstruct)

    p_rep = sub.add_parser("report", help="locate the latest report for a symbol/date")
    p_rep.add_argument("--symbol", default="AAPL")
    p_rep.add_argument("--date", default="2025-05-15")
    p_rep.add_argument("--db", default=None, help="path to the SQLite file")
    p_rep.set_defaults(func=_cmd_report)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
