import json

from same_day_lab import cli
from same_day_lab.reports.verdict import ALLOWED_VERDICTS


def _run_pipeline(tmp_path, symbol="AAPL", date="2025-05-15"):
    db = str(tmp_path / "lab.sqlite3")
    assert cli.main(["init-db", "--db", db]) == 0
    assert cli.main(["ingest", "--provider", "fixture", "--symbol", symbol, "--date", date, "--db", db]) == 0
    assert cli.main(["run", "--symbol", symbol, "--date", date, "--db", db]) == 0
    return db


def test_end_to_end_report(tmp_path):
    _run_pipeline(tmp_path)
    jsons = list((tmp_path / "reports").glob("*.json"))
    mds = list((tmp_path / "reports").glob("*.md"))
    assert len(jsons) == 1 and len(mds) == 1

    rep = json.loads(jsons[0].read_text())
    md = mds[0].read_text()

    # DATA WARNING is the first content block in both.
    assert list(rep.keys())[0] == "data_warning"
    assert md.lstrip().startswith("DATA WARNING")

    # explicit no-lookahead proof
    assert rep["no_lookahead_proof"]["distinct"] is True

    # verdict in the allowed set, and naive can never be the basis of PASS here
    assert rep["verdict"] in ALLOWED_VERDICTS

    # friction sweep + crossover present
    assert len(rep["friction_sweep"]) == 5 * 4
    assert rep["crossover"]["crossover_cents"] == 5

    # naive >= pessimistic, smoke-test note present
    assert rep["trade"]["naive"]["pnl"] >= rep["trade"]["pessimistic"]["pnl"]
    assert rep["note"] == "ORB is a smoke test, not a validated edge."

    # markdown carries the human-readable essentials
    assert "Friction sweep" in md
    assert rep["verdict"] in md
    assert "Naive fills are a labeled lie" in md


def test_run_requires_prior_ingest(tmp_path):
    db = str(tmp_path / "lab.sqlite3")
    assert cli.main(["init-db", "--db", db]) == 0
    # no ingest -> run should fail gracefully (non-zero), not raise
    assert cli.main(["run", "--symbol", "AAPL", "--date", "2025-05-15", "--db", db]) == 1
