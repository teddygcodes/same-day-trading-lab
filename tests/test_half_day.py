import json

from same_day_lab import cli
from same_day_lab.config import load_config
from same_day_lab.ingest.fixture import load_fixture
from same_day_lab.ingest.normalize import build_session, normalize_bars
from same_day_lab.quality.summary import evaluate
from same_day_lab.storage import sqlite as db


def test_complete_half_day_is_valid_not_partial(tmp_path):
    dbp = str(tmp_path / "lab.sqlite3")
    assert cli.main(["init-db", "--db", dbp]) == 0
    assert cli.main(["ingest", "--provider", "fixture", "--symbol", "AAPL", "--date", "2025-11-28", "--db", dbp]) == 0

    conn = db.connect(dbp)
    row = db.get_session(conn, "AAPL", "2025-11-28")
    assert row["is_half_day"] == 1
    assert row["bar_count_expected"] == 210
    assert row["bar_count_actual"] == 210
    summary = json.loads(row["quality_summary_json"])
    assert summary["partial_session"] is False


def test_truncated_half_day_is_partial_and_invalid():
    cfg = load_config()
    payload = dict(load_fixture("AAPL", "2025-11-28"))
    payload["bars"] = payload["bars"][:200]  # drop the last 10 bars

    bars = normalize_bars(payload, cfg, provider="fixture")
    session = build_session(payload, bars, cfg)
    _per_bar, summary, data_valid, reasons = evaluate(bars, session, cfg)

    assert session.bar_count_expected == 210
    assert session.bar_count_actual == 200
    assert summary["partial_session"] is True
    assert data_valid is False
    assert any("partial" in r.lower() for r in reasons)
