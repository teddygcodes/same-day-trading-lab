import json

from same_day_lab import cli
from same_day_lab.storage import sqlite as db

MESSY_DATE = "2025-06-16"


def _ingest_run(dbp):
    assert cli.main(["init-db", "--db", dbp]) == 0
    assert cli.main(["ingest", "--provider", "fixture", "--symbol", "AAPL", "--date", MESSY_DATE, "--db", dbp]) == 0
    assert cli.main(["run", "--symbol", "AAPL", "--date", MESSY_DATE, "--db", dbp]) == 0
    conn = db.connect(dbp)
    row = db.latest_run(conn, "AAPL", MESSY_DATE)
    with open(row["report_json_path"]) as f:
        return json.load(f)


def test_messy_fixture_replays_to_valid_deterministic_report(tmp_path):
    rep = _ingest_run(str(tmp_path / "lab.sqlite3"))
    qs = rep["quality_summary"]

    # IEX gaps are NON-fatal and prominently surfaced
    assert rep["verdict"] != "INVALID_DATA"
    assert rep["data_valid"] is True
    assert qs["missing_bar_count"] == 16
    assert len(qs["missing_bars"]) == 16
    # halt detected and non-fatal
    assert qs["halt_suspected"] is True
    assert len(qs["halt_runs"]) == 1 and len(qs["halt_runs"][0]) == 12
    assert qs["partial_session"] is False
    # fills exercised, and the extreme-move / zero-volume bars are present + flagged
    assert rep["trade"] is not None
    assert qs["extreme_move_count"] == 1 and qs["zero_volume_count"] == 1
    # honesty guard: the friction sweep still crosses zero (the edge dies under
    # friction). If the extreme-move spike leaked into bars_after_signal it would
    # be mis-read as a target hit and prop P&L up, erasing the crossover.
    assert rep["crossover"]["crossover_cents"] is not None
    # NO fabricated bars: present == expected - missing
    assert rep["bars"]["actual"] == rep["bars"]["expected"] - qs["missing_bar_count"]


def test_messy_fixture_two_runs_identical_report_hash(tmp_path):
    h1 = _ingest_run(str(tmp_path / "a.sqlite3"))["report_hash"]
    h2 = _ingest_run(str(tmp_path / "b.sqlite3"))["report_hash"]
    assert h1 == h2 and len(h1) == 64
