"""Command-line entry point.

Subcommands: init-db, ingest, run, run-range, tournament, reconstruct, report. This
module only parses arguments and dispatches to the pipeline modules.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from . import DATA_WARNING, runner
from .config import config_hash, load_config
from .ingest import alpaca, fixture
from .ingest.normalize import build_session, normalize_bars
from .ingest.raw_archive import archive_raw
from .quality.summary import evaluate
from .replay.reconstruct import reconstruct
from .storage import sqlite as db
from .strategy import DEFAULT_STRATEGY, STRATEGIES

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
    conn = db.connect(args.db)
    db.init_db(conn)

    result = runner.run_one_day(
        conn, args.symbol, args.date, config, reports_dir=_reports_dir(args.db),
        strategy=args.strategy,
    )
    if result.get("missing_ingest"):
        print(
            f"run failed: no ingest for {args.symbol} {args.date}; run `ingest` first",
            file=sys.stderr,
        )
        return 1

    print(f"verdict: {result['verdict']}")
    print(f"  report json: {result['report_json_path']}")
    print(f"  report md:   {result['report_md_path']}")
    print(f"  report_hash: {result['report_hash'][:16]}...")
    return 0


def _cmd_run_range(args) -> int:
    config = load_config()
    conn = db.connect(args.db)
    db.init_db(conn)

    agg = runner.run_range(
        conn, args.symbol, args.start, args.end, config, reports_dir=_reports_dir(args.db),
        strategy=args.strategy,
    )
    c = agg["counts"]
    print(
        f"aggregate {args.symbol} {args.start}→{args.end}: "
        f"{c['days_ingested']} day(s) ingested, {c['traded']} traded, "
        f"KILL {c['traded_killed_by_friction']}, survived-pass {c['traded_survived_pass_threshold']}"
    )
    if agg["missing_weekdays"]:
        print(f"  missing weekdays (no ingest): {', '.join(agg['missing_weekdays'])}")
    print(f"  fill-honesty headline: {agg['fill_honesty_headline']} day(s) naive>0 but pessimistic killed")
    print(f"  aggregate json: {agg['aggregate_json_path']}")
    print(f"  aggregate md:   {agg['aggregate_md_path']}")
    print(f"  aggregate_hash: {agg['aggregate_hash'][:16]}...")
    return 0


def _cmd_tournament(args) -> int:
    config = load_config()
    conn = db.connect(args.db)
    db.init_db(conn)

    t = runner.run_tournament(
        conn, args.symbol, decide_start=args.decide_start, decide_end=args.decide_end,
        holdout_start=args.holdout_start, holdout_end=args.holdout_end, config=config,
        reports_dir=_reports_dir(args.db),
    )
    print(
        f"tournament {args.symbol}: {t['n_strategies']} strategies evaluated over "
        f"decide {args.decide_start}→{args.decide_end} and holdout "
        f"{args.holdout_start}→{args.holdout_end}"
    )
    print(f"  CAVEAT: {t['multiple_comparisons_caveat']}")
    for row in t["leaderboard"]:
        print(
            f"  {row['strategy']}: decide survives={row['decide']['survives']}, "
            f"holdout survives={row['holdout']['survives']} → carried_forward="
            f"{row['carried_forward']}"
        )
    for label, key in (("decide", "decide_window"), ("holdout", "holdout_window")):
        miss = t[key]["missing_weekdays"]
        if miss:
            print(f"  missing weekdays ({label}, no ingest): {', '.join(miss)}")
    print(f"  tournament json: {t['tournament_json_path']}")
    print(f"  tournament md:   {t['tournament_md_path']}")
    print(f"  tournament_hash: {t['tournament_hash'][:16]}...")
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

    p_run = sub.add_parser("run", help="replay + strategy + dual fills + report")
    p_run.add_argument("--symbol", default="AAPL")
    p_run.add_argument("--date", default="2025-05-15")
    p_run.add_argument(
        "--strategy", choices=sorted(STRATEGIES), default=DEFAULT_STRATEGY,
        help="registered strategy name (default: %(default)s)",
    )
    p_run.add_argument("--db", default=None, help="path to the SQLite file")
    p_run.set_defaults(func=_cmd_run)

    p_range = sub.add_parser(
        "run-range",
        help="replay each ingested day in a range independently + aggregate distribution",
        description="Per-day independent (own clock/OR/one-trade; no carry-over, no "
        "compounding). Descriptive counts only — no aggregate verdict.",
    )
    p_range.add_argument("--symbol", default="AAPL")
    p_range.add_argument("--start", required=True, help="range start, YYYY-MM-DD (inclusive)")
    p_range.add_argument("--end", required=True, help="range end, YYYY-MM-DD (inclusive)")
    p_range.add_argument(
        "--strategy", choices=sorted(STRATEGIES), default=DEFAULT_STRATEGY,
        help="registered strategy name (default: %(default)s)",
    )
    p_range.add_argument("--db", default=None, help="path to the SQLite file")
    p_range.set_defaults(func=_cmd_run_range)

    p_tourn = sub.add_parser(
        "tournament",
        help="evaluate the full registered strategy set over a decide + holdout window",
        description="Descriptive cross-strategy × cross-window leaderboard. Evaluates the "
        "WHOLE registered set (no subset flag — choosing after peeking is the bias this "
        "guards against). 'Carried forward' = survives both windows; this is a flag, not a "
        "verdict. No tournament winner / validation verdict.",
    )
    p_tourn.add_argument("--symbol", default="AAPL")
    p_tourn.add_argument("--decide-start", required=True, help="decide window start, YYYY-MM-DD")
    p_tourn.add_argument("--decide-end", required=True, help="decide window end, YYYY-MM-DD")
    p_tourn.add_argument("--holdout-start", required=True, help="holdout window start, YYYY-MM-DD")
    p_tourn.add_argument("--holdout-end", required=True, help="holdout window end, YYYY-MM-DD")
    p_tourn.add_argument("--db", default=None, help="path to the SQLite file")
    p_tourn.set_defaults(func=_cmd_tournament)

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
