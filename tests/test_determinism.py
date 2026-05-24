import json

from same_day_lab import cli


def test_two_runs_produce_identical_report_hash(tmp_path):
    db = str(tmp_path / "lab.sqlite3")
    assert cli.main(["init-db", "--db", db]) == 0
    assert cli.main(["ingest", "--provider", "fixture", "--symbol", "AAPL", "--date", "2025-05-15", "--db", db]) == 0
    assert cli.main(["run", "--symbol", "AAPL", "--date", "2025-05-15", "--db", db]) == 0
    assert cli.main(["run", "--symbol", "AAPL", "--date", "2025-05-15", "--db", db]) == 0

    reports = sorted((tmp_path / "reports").glob("*.json"))
    assert len(reports) == 2
    r1, r2 = (json.loads(p.read_text()) for p in reports)

    # the deterministic core is identical across runs
    assert r1["report_hash"] == r2["report_hash"]
    assert len(r1["report_hash"]) == 64
    for key in (
        "strategy",
        "strategy_context",
        "trade",
        "friction_sweep",
        "crossover",
        "verdict",
        "pessimistic_default_pnl",
        "pessimistic_pass_pnl",
        "quality_summary",
    ):
        assert r1[key] == r2[key]

    # volatile fields differ but do NOT affect report_hash (excluded from the core)
    assert r1["run"]["run_id"] != r2["run"]["run_id"]
