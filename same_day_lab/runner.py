"""Orchestration shared by the ``run`` (single day) and ``run-range`` (multi-day)
commands. ``cli.py`` only parses args and dispatches here.

Per-day independence is structural: ``run_range`` calls ``run_one_day`` once per
ingested date, each with its own DB read, its own ``ReplayClock`` (inside
``run_replay``), its own opening range and one-trade-per-day. Nothing carries between
days — no position, capital, or compounding.
"""

import json
import uuid
from datetime import date, datetime, timedelta, timezone

from .config import config_hash
from .fills.sweep import pnl_at
from .hashing import content_hash
from .ingest.normalize import build_session, normalize_bars
from .quality.summary import evaluate
from .replay import run_replay
from .reports.aggregate import build_aggregate, write_aggregate
from .reports.tournament import build_tournament, write_tournament
from .reports.verdict import decide_verdict
from .reports.writer import build_report, write_reports
from .storage import sqlite as db
from .strategy import DEFAULT_STRATEGY, STRATEGIES


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def weekdays_in_range(start: str, end: str) -> list[str]:
    """ISO ``YYYY-MM-DD`` Mon–Fri dates with ``start <= d <= end`` (inclusive).

    Uses only the Gregorian weekday (``date.weekday() < 5``) — NOT a market
    calendar, so holidays are *not* filtered out (they surface as missing days,
    which the caller reports for the operator to record or judge). Empty if
    ``start > end``.
    """
    lo = date.fromisoformat(start)
    hi = date.fromisoformat(end)
    out: list[str] = []
    d = lo
    while d <= hi:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def run_one_day(
    conn, symbol: str, date: str, config: dict, *, reports_dir: str,
    strategy: str = DEFAULT_STRATEGY, write_report_file: bool = True,
) -> dict:
    """Replay one fully isolated (symbol, date): fills → verdict → report → persist.

    Returns the per-day analytics (including ``report_hash`` and the full report).
    A date with no ingest returns ``{"missing_ingest": True, ...}`` (the caller
    decides how to surface it) — never fabricates or substitutes data.

    ``write_report_file`` controls only whether the per-day JSON+MD *file* is written:
    the single-day ``run`` command leaves it ``True``; rollups (``run_range`` /
    ``run_tournament``) pass ``False`` to avoid littering ``reports/`` with incidental
    per-day files. The report dict is built and the per-day ``runs``/``trades`` DB rows
    are persisted either way — when no file is written the row's report paths are empty
    (no dangling path), not a path to a nonexistent file.
    """
    cfg_hash = config_hash(config)
    ing = db.get_ingest_run(conn, symbol, date)
    if ing is None:
        return {"missing_ingest": True, "symbol": symbol, "session_date": date}

    with open(ing["raw_path"]) as f:
        payload = json.load(f)["raw_payload"]
    bars = normalize_bars(payload, config, provider=ing["provider"])
    session = build_session(payload, bars, config)
    _per_bar, summary, data_valid, reasons = evaluate(bars, session, config)
    rth = [b for b in bars if b.is_regular_market_hours]

    started = _now()
    rr = run_replay(rth, config, flatten_ts=session.flatten_ts, strategy=strategy)
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

    run_id = f"run_{symbol}_{session.session_date}_{uuid.uuid4().hex[:8]}"
    completed = _now()
    report = build_report(
        run_id=run_id,
        symbol=symbol,
        session_date=session.session_date,
        strategy=strategy,
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
    if write_report_file:
        json_path, md_path = write_reports(report, reports_dir)
    else:
        json_path = md_path = ""  # no file → empty path in the runs row, never a dangling one

    db.insert_run(
        conn,
        {
            "run_id": run_id,
            "ingest_run_id": ing["ingest_run_id"],
            "symbol": symbol,
            "session_date": session.session_date,
            "strategy_name": strategy,
            "strategy_config_hash": content_hash({"strategy": strategy, "orb": config.get("orb")}),
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
                "symbol": symbol,
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

    crossover = rr.get("crossover")
    return {
        "missing_ingest": False,
        "symbol": symbol,
        "session_date": session.session_date,
        "verdict": verdict,
        "data_valid": data_valid,
        "replay_valid": rr["replay_valid"],
        "traded": trade is not None,
        "exit_reason": trade.exit_reason if trade is not None else None,
        "naive_pnl": naive_pnl,
        "pessimistic_default_pnl": pess_default,
        "pessimistic_pass_pnl": pess_pass,
        "crossover_cents": crossover.get("crossover_cents") if crossover else None,
        "report_hash": report["report_hash"],
        "report": report,
        "report_json_path": json_path,
        "report_md_path": md_path,
    }


def aggregate_range(
    conn, symbol: str, start: str, end: str, config: dict, *, reports_dir: str,
    strategy: str = DEFAULT_STRATEGY,
) -> dict:
    """Replay every ingested day in ``[start, end]`` independently and build the
    aggregate **in memory** (no sub-aggregate file written).

    Days are the **ingested** dates in range (deduped by ``session_date``); each is
    replayed via ``run_one_day`` with ``write_report_file=False`` — it persists per-day
    ``runs``/``trades`` DB rows but writes no incidental per-day report files (the
    aggregate is the deliverable). Weekdays in range with no ingest are reported as
    missing — never invented. The returned dict has no ``aggregate_*_path`` keys; callers
    that want files on disk use ``run_range``.
    """
    rows = db.get_ingest_runs_in_range(conn, symbol, start, end)
    dates = sorted({r["session_date"] for r in rows})
    per_day = [
        run_one_day(
            conn, symbol, d, config, reports_dir=reports_dir, strategy=strategy,
            write_report_file=False,
        )
        for d in dates
    ]
    ingested = set(dates)
    missing = [d for d in weekdays_in_range(start, end) if d not in ingested]

    return build_aggregate(
        symbol=symbol,
        start=start,
        end=end,
        strategy=strategy,
        config_hash=config_hash(config),
        per_day=per_day,
        missing_weekdays=missing,
    )


def run_range(
    conn, symbol: str, start: str, end: str, config: dict, *, reports_dir: str,
    strategy: str = DEFAULT_STRATEGY,
) -> dict:
    """Replay every ingested day in ``[start, end]`` independently and aggregate,
    writing the aggregate JSON + Markdown to ``reports_dir``."""
    aggregate = aggregate_range(
        conn, symbol, start, end, config, reports_dir=reports_dir, strategy=strategy
    )
    json_path, md_path = write_aggregate(aggregate, reports_dir)
    aggregate["aggregate_json_path"] = json_path
    aggregate["aggregate_md_path"] = md_path
    return aggregate


def run_tournament(
    conn, symbol: str, *, decide_start: str, decide_end: str, holdout_start: str,
    holdout_end: str, config: dict, reports_dir: str,
) -> dict:
    """Evaluate the **entire** registered strategy set over a decide window and a
    holdout window, and emit a descriptive leaderboard with a corroboration flag.

    For each registered strategy × each window the per-strategy aggregate is computed
    **in memory** via ``aggregate_range`` (no sub-aggregate files written); the
    tournament is a thin cross-strategy × cross-window rollup that forks no fill/verdict
    logic. Evaluating the whole set — never a peeked subset — is the anti-selection-bias
    point, so there is no strategy-subset argument.
    """
    strategies = sorted(STRATEGIES)
    decide_window = {"start": decide_start, "end": decide_end}
    holdout_window = {"start": holdout_start, "end": holdout_end}

    results = {
        s: {
            "decide": aggregate_range(
                conn, symbol, decide_start, decide_end, config,
                reports_dir=reports_dir, strategy=s,
            ),
            "holdout": aggregate_range(
                conn, symbol, holdout_start, holdout_end, config,
                reports_dir=reports_dir, strategy=s,
            ),
        }
        for s in strategies
    }

    tournament = build_tournament(
        symbol=symbol,
        config_hash=config_hash(config),
        decide_window=decide_window,
        holdout_window=holdout_window,
        strategies=strategies,
        results=results,
    )
    json_path, md_path = write_tournament(tournament, reports_dir)
    tournament["tournament_json_path"] = json_path
    tournament["tournament_md_path"] = md_path
    return tournament
