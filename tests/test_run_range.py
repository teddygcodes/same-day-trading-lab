"""v0.3 multi-day aggregate: storage range query, weekday enumeration, and the
run-range aggregate (counts, determinism, per-day independence, missing days)."""

from same_day_lab import cli, runner
from same_day_lab.config import load_config
from same_day_lab.runner import weekdays_in_range
from same_day_lab.storage import sqlite as db

# Synthetic multi-day mix (2025-07-07 Mon .. 07-10 Thu); 07-11 Fri intentionally absent.
FIXTURE_VERDICTS = {
    "2025-07-07": "PASS_FOR_MORE_TESTING",  # survives friction
    "2025-07-08": "KILL_STRATEGY",          # naive>0 but pessimistic kills it
    "2025-07-09": "HOLD_MORE_DATA",          # no breakout signal
    "2025-07-10": "INVALID_DATA",            # partial session (leading gap)
}


def _setup_range_db(tmp_path):
    db_path = str(tmp_path / "lab.sqlite3")
    assert cli.main(["init-db", "--db", db_path]) == 0
    for d in FIXTURE_VERDICTS:
        assert cli.main(
            ["ingest", "--provider", "fixture", "--symbol", "AAPL", "--date", d, "--db", db_path]
        ) == 0
    return db_path


def _ingest_row(symbol, date):
    return {
        "ingest_run_id": f"ing_{symbol}_{date}",
        "provider": "fixture",
        "symbol": symbol,
        "session_date": date,
        "fetch_ts_utc": "2025-01-01T00:00:00+00:00",
        "raw_path": "/dev/null",
        "raw_hash": "deadbeef",
        "config_hash": "cafef00d",
        "source_warning": "WARNING",
        "created_at_utc": "2025-01-01T00:00:00+00:00",
    }


def test_get_ingest_runs_in_range(tmp_path):
    conn = db.connect(str(tmp_path / "lab.sqlite3"))
    db.init_db(conn)
    for d in ("2025-07-06", "2025-07-07", "2025-07-09", "2025-07-12"):
        db.insert_ingest_run(conn, _ingest_row("AAPL", d))
    db.insert_ingest_run(conn, _ingest_row("MSFT", "2025-07-08"))  # other symbol, in range

    rows = db.get_ingest_runs_in_range(conn, "AAPL", "2025-07-07", "2025-07-10")
    dates = [r["session_date"] for r in rows]

    # inclusive bounds, only AAPL, ascending order, endpoints excluded outside range
    assert dates == ["2025-07-07", "2025-07-09"]


def test_weekdays_in_range_skips_weekends():
    # 2025-07-07 Mon .. 2025-07-13 Sun -> only Mon-Fri
    assert weekdays_in_range("2025-07-07", "2025-07-13") == [
        "2025-07-07", "2025-07-08", "2025-07-09", "2025-07-10", "2025-07-11",
    ]


def test_weekdays_in_range_single_weekday_and_weekend():
    assert weekdays_in_range("2025-07-09", "2025-07-09") == ["2025-07-09"]  # Wed
    assert weekdays_in_range("2025-07-12", "2025-07-12") == []              # Sat


def test_weekdays_in_range_empty_when_start_after_end():
    assert weekdays_in_range("2025-07-11", "2025-07-07") == []


def test_per_day_verdicts_for_synthetic_mix(tmp_path):
    db_path = _setup_range_db(tmp_path)
    conn = db.connect(db_path)
    config = load_config()
    reports_dir = str(tmp_path / "reports")
    results = {
        d: runner.run_one_day(conn, "AAPL", d, config, reports_dir=reports_dir)
        for d in FIXTURE_VERDICTS
    }
    for d, expected in FIXTURE_VERDICTS.items():
        assert results[d]["verdict"] == expected, (d, results[d]["verdict"])

    # the fill-honesty mechanics the mix is built to exercise
    assert results["2025-07-07"]["pessimistic_pass_pnl"] > 0       # survives the pass threshold
    assert results["2025-07-08"]["naive_pnl"] > 0                  # naive looked profitable
    assert results["2025-07-08"]["pessimistic_default_pnl"] <= 0   # pessimistic killed it
    assert results["2025-07-09"]["traded"] is False                # no signal
    assert results["2025-07-10"]["data_valid"] is False            # invalid data


def test_run_range_aggregate_counts_and_no_verdict(tmp_path):
    conn = db.connect(_setup_range_db(tmp_path))
    agg = runner.run_range(
        conn, "AAPL", "2025-07-07", "2025-07-11", load_config(), reports_dir=str(tmp_path / "reports")
    )
    c = agg["counts"]
    assert c["days_ingested"] == 4
    assert c["invalid_data"] == 1
    assert c["no_signal"] == 1
    assert c["traded"] == 2
    assert c["traded_naive_gt0"] == 2
    assert c["traded_pessimistic_default_gt0"] == 1
    assert c["traded_survived_pass_threshold"] == 1
    assert c["traded_killed_by_friction"] == 1
    assert agg["fill_honesty_headline"] == 1
    assert agg["missing_weekdays"] == ["2025-07-11"]  # Fri in range, never ingested
    assert agg["crossover_cents_distribution"] == {"none": 1, "0": 1}

    # descriptive distribution only — there is NO aggregate validation verdict
    assert "verdict" not in agg
    assert "no aggregate validation verdict" in agg["note"]
    assert agg["data_warning"]  # DATA WARNING is carried on the report


def test_run_range_aggregate_hash_is_deterministic(tmp_path):
    conn = db.connect(_setup_range_db(tmp_path))
    cfg = load_config()
    rd = str(tmp_path / "reports")
    a1 = runner.run_range(conn, "AAPL", "2025-07-07", "2025-07-11", cfg, reports_dir=rd)
    a2 = runner.run_range(conn, "AAPL", "2025-07-07", "2025-07-11", cfg, reports_dir=rd)
    assert a1["aggregate_hash"] == a2["aggregate_hash"]
    assert len(a1["aggregate_hash"]) == 64


def test_per_day_independence(tmp_path):
    conn = db.connect(_setup_range_db(tmp_path))
    cfg = load_config()
    rd = str(tmp_path / "reports")

    # the trade day's fingerprint inside the full range
    full = runner.run_range(conn, "AAPL", "2025-07-07", "2025-07-11", cfg, reports_dir=rd)
    in_range = {p["date"]: p["report_hash"] for p in full["per_day"]}

    # ...is identical to running that day entirely alone
    alone = runner.run_one_day(conn, "AAPL", "2025-07-07", cfg, reports_dir=rd)["report_hash"]
    assert in_range["2025-07-07"] == alone

    # ...and is unaffected by replaying the preceding KILL day first (no carry-over)
    runner.run_one_day(conn, "AAPL", "2025-07-08", cfg, reports_dir=rd)
    after = runner.run_one_day(conn, "AAPL", "2025-07-07", cfg, reports_dir=rd)["report_hash"]
    assert after == alone


def test_run_range_missing_lists_weekdays_not_weekends(tmp_path):
    conn = db.connect(_setup_range_db(tmp_path))
    # 2025-07-07 Mon .. 07-13 Sun: 07-11 Fri is missing; 07-12 Sat / 07-13 Sun are NOT listed
    agg = runner.run_range(
        conn, "AAPL", "2025-07-07", "2025-07-13", load_config(), reports_dir=str(tmp_path / "reports")
    )
    assert agg["missing_weekdays"] == ["2025-07-11"]


def test_run_range_cli_end_to_end(tmp_path):
    db_path = _setup_range_db(tmp_path)
    assert cli.main(
        ["run-range", "--symbol", "AAPL", "--start", "2025-07-07", "--end", "2025-07-11", "--db", db_path]
    ) == 0
    aggs = sorted((tmp_path / "reports").glob("*_aggregate.json"))
    assert len(aggs) == 1
