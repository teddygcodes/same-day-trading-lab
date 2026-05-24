"""v0.4b honest tournament: a descriptive cross-strategy × cross-window leaderboard
with a holdout corroboration flag and a prominent multiple-comparisons caveat.

The two-window synthetic fixtures (tools/gen_fixture.py) are engineered so the three
registered strategies show a deliberate spread under the counts-only "survives a window"
rule (>=1 PASS day AND 0 KILL days):

  or_fade_long       -> survives BOTH windows  -> carried_forward (the breakdown→reclaim
                        long PASSes in the decide and holdout windows).
  orb_long_5m        -> survives the decide window, but a holdout KILL day drops it: the
                        holdout gate visibly bites (carried_forward False).
  vwap_reclaim_long  -> never PASSes either window -> no-signal / no corroboration.

There is NO tournament winner / validation verdict — only the per-strategy flag.
"""

import json

from same_day_lab import cli, runner
from same_day_lab.config import load_config
from same_day_lab.reports.tournament import SURVIVES_RULE
from same_day_lab.storage import sqlite as db
from same_day_lab.strategy import STRATEGIES

DECIDE = ("2025-08-04", "2025-08-08")
HOLDOUT = ("2025-08-11", "2025-08-15")
INGEST_DATES = ["2025-08-04", "2025-08-05", "2025-08-11", "2025-08-12"]

# The engineered spread (the fixtures are the source of truth; this pins the intent).
EXPECTED = {
    "or_fade_long": {"decide": True, "holdout": True, "carried": True},
    "orb_long_5m": {"decide": True, "holdout": False, "carried": False},
    "vwap_reclaim_long": {"decide": False, "holdout": False, "carried": False},
}

# math the lab forbids in any rollup (CLAUDE.md prohibition) — must appear nowhere.
# ("equity curve" as a phrase so it doesn't collide with the DATA WARNING's "equity market".)
_FORBIDDEN = ("sharpe", "sortino", "drawdown", "equity curve", "portfolio", "annualized")


def _setup(tmp_path):
    db_path = str(tmp_path / "lab.sqlite3")
    assert cli.main(["init-db", "--db", db_path]) == 0
    for d in INGEST_DATES:
        assert cli.main(
            ["ingest", "--provider", "fixture", "--symbol", "AAPL", "--date", d, "--db", db_path]
        ) == 0
    return db_path


def _tournament(tmp_path):
    conn = db.connect(_setup(tmp_path))
    return runner.run_tournament(
        conn, "AAPL", decide_start=DECIDE[0], decide_end=DECIDE[1],
        holdout_start=HOLDOUT[0], holdout_end=HOLDOUT[1], config=load_config(),
        reports_dir=str(tmp_path / "reports"),
    )


def _row(report, strategy):
    return next(r for r in report["leaderboard"] if r["strategy"] == strategy)


def test_whole_registered_set_is_evaluated(tmp_path):
    t = _tournament(tmp_path)
    # The entire registered set — never a peeked subset — is the anti-selection-bias point.
    assert t["n_strategies"] == len(STRATEGIES) == 3
    assert t["strategies_evaluated"] == sorted(STRATEGIES)
    assert sorted(r["strategy"] for r in t["leaderboard"]) == sorted(STRATEGIES)


def test_leaderboard_counts_match_independent_run_range(tmp_path):
    """The leaderboard is a faithful rollup: each (strategy, window) summary equals an
    independent run_range over that window — guaranteeing it forks no fill/verdict logic."""
    conn = db.connect(_setup(tmp_path))
    cfg = load_config()
    rd = str(tmp_path / "reports")
    t = runner.run_tournament(
        conn, "AAPL", decide_start=DECIDE[0], decide_end=DECIDE[1],
        holdout_start=HOLDOUT[0], holdout_end=HOLDOUT[1], config=cfg, reports_dir=rd,
    )
    for strategy in STRATEGIES:
        row = _row(t, strategy)
        for window_key, (start, end) in (("decide", DECIDE), ("holdout", HOLDOUT)):
            agg = runner.run_range(conn, "AAPL", start, end, cfg, reports_dir=rd, strategy=strategy)
            summary = row[window_key]
            assert summary["days_traded"] == agg["counts"]["traded"]
            assert summary["survived_pass"] == agg["counts"]["traded_survived_pass_threshold"]
            assert summary["killed"] == agg["counts"]["traded_killed_by_friction"]
            assert summary["fill_honesty"] == agg["fill_honesty_headline"]
            assert summary["aggregate_hash"] == agg["aggregate_hash"]


def test_carried_forward_requires_both_windows(tmp_path):
    t = _tournament(tmp_path)
    for strategy, exp in EXPECTED.items():
        row = _row(t, strategy)
        assert row["decide"]["survives"] is exp["decide"], strategy
        assert row["holdout"]["survives"] is exp["holdout"], strategy
        assert row["carried_forward"] is exp["carried"], strategy
        # carried_forward is exactly "survives BOTH windows" — never one window alone.
        assert row["carried_forward"] == (row["decide"]["survives"] and row["holdout"]["survives"])

    flags = {s: _row(t, s)["carried_forward"] for s in STRATEGIES}
    # The engineered trichotomy is present: one carried, one survives-decide-only
    # (holdout gate bites), one never.
    assert flags["or_fade_long"] is True
    assert _row(t, "orb_long_5m")["decide"]["survives"] is True
    assert _row(t, "orb_long_5m")["holdout"]["survives"] is False  # gate bites
    assert _row(t, "vwap_reclaim_long")["decide"]["survives"] is False


def test_multiple_comparisons_caveat_states_N(tmp_path):
    t = _tournament(tmp_path)
    caveat = t["multiple_comparisons_caveat"]
    assert str(t["n_strategies"]) in caveat  # N stated explicitly
    assert "holdout" in caveat.lower()
    assert "weak" in caveat.lower()


def test_survives_rule_is_stated(tmp_path):
    t = _tournament(tmp_path)
    assert t["survives_rule"] == SURVIVES_RULE
    assert "PASS_FOR_MORE_TESTING" in t["survives_rule"]
    assert "KILL_STRATEGY" in t["survives_rule"]


def test_no_winner_or_validation_verdict(tmp_path):
    t = _tournament(tmp_path)
    assert "verdict" not in t
    assert "winner" not in t
    for row in t["leaderboard"]:
        assert "verdict" not in row and "winner" not in row
    blob = json.dumps(t).lower()
    for word in _FORBIDDEN:
        assert word not in blob, word


def test_tournament_hash_is_deterministic(tmp_path):
    t1 = _tournament(tmp_path)
    t2 = _tournament(tmp_path)
    assert t1["tournament_hash"] == t2["tournament_hash"]
    assert len(t1["tournament_hash"]) == 64


def test_missing_weekdays_surfaced_per_window_not_fabricated(tmp_path):
    t = _tournament(tmp_path)
    # Decide ingested 08-04/08-05 -> 08-06/07/08 missing; weekend not listed.
    assert t["decide_window"]["missing_weekdays"] == ["2025-08-06", "2025-08-07", "2025-08-08"]
    # Holdout ingested 08-11/08-12 -> 08-13/14/15 missing.
    assert t["holdout_window"]["missing_weekdays"] == ["2025-08-13", "2025-08-14", "2025-08-15"]


def test_report_files_data_warning_and_caveat(tmp_path):
    t = _tournament(tmp_path)
    with open(t["tournament_md_path"]) as f:
        md = f.read()
    assert md.startswith("DATA WARNING:")  # the first block of every report
    assert t["multiple_comparisons_caveat"] in md
    assert "carried_forward" in md
    with open(t["tournament_json_path"]) as f:
        assert json.load(f)["tournament_hash"] == t["tournament_hash"]


def test_cli_end_to_end(tmp_path):
    db_path = _setup(tmp_path)
    assert cli.main(
        ["tournament", "--symbol", "AAPL", "--decide-start", DECIDE[0], "--decide-end", DECIDE[1],
         "--holdout-start", HOLDOUT[0], "--holdout-end", HOLDOUT[1], "--db", db_path]
    ) == 0
    files = sorted((tmp_path / "reports").glob("*_tournament.json"))
    assert len(files) == 1
