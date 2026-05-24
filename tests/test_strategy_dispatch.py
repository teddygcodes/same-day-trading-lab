"""CLI --strategy dispatch: each registered strategy runs deterministically through the
single-day and range pipelines and records its own name in the report."""

import json

from same_day_lab import cli
from same_day_lab.strategy import STRATEGIES

DATE = "2025-05-15"


def _ingest(db):
    assert cli.main(["init-db", "--db", db]) == 0
    assert cli.main(
        ["ingest", "--provider", "fixture", "--symbol", "AAPL", "--date", DATE, "--db", db]
    ) == 0


def test_run_dispatch_is_deterministic_and_records_strategy(tmp_path):
    hashes = {}
    for name in sorted(STRATEGIES):
        d = tmp_path / name
        d.mkdir()
        db = str(d / "lab.sqlite3")
        _ingest(db)
        for _ in range(2):  # two runs of the same strategy
            assert cli.main(
                ["run", "--symbol", "AAPL", "--date", DATE, "--strategy", name, "--db", db]
            ) == 0

        reports = sorted((d / "reports").glob("*.json"))
        assert len(reports) == 2
        r1, r2 = (json.loads(p.read_text()) for p in reports)
        assert r1["report_hash"] == r2["report_hash"]   # deterministic
        assert len(r1["report_hash"]) == 64
        assert r1["strategy"] == name                   # hashed core records the name
        assert r1["run"]["strategy"] == name
        hashes[name] = r1["report_hash"]

    # the three strategies are distinguishable — the hashed `strategy` field guarantees it.
    assert len(set(hashes.values())) == len(STRATEGIES)


def test_unknown_strategy_is_rejected_by_the_cli(tmp_path):
    db = str(tmp_path / "lab.sqlite3")
    _ingest(db)
    # argparse `choices` rejects an unregistered name with a non-zero exit (SystemExit).
    try:
        rc = cli.main(["run", "--symbol", "AAPL", "--date", DATE, "--strategy", "bogus", "--db", db])
    except SystemExit as exc:
        rc = exc.code
    assert rc != 0


def test_run_range_dispatch_carries_strategy_and_no_verdict(tmp_path):
    db = str(tmp_path / "lab.sqlite3")
    _ingest(db)
    for name in sorted(STRATEGIES):
        assert cli.main(
            ["run-range", "--symbol", "AAPL", "--start", DATE, "--end", DATE,
             "--strategy", name, "--db", db]
        ) == 0
    agg = json.loads(
        sorted((tmp_path / "reports").glob("*_aggregate.json"))[-1].read_text()
    )
    assert agg["strategy"] in STRATEGIES
    assert "verdict" not in agg   # no aggregate validation verdict (v0.3 stance preserved)
