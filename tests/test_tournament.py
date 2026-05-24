"""v0.4b honest tournament (v0.4b.1 fraction gate): a descriptive cross-strategy ×
cross-window leaderboard with a holdout corroboration flag and a prominent
multiple-comparisons caveat.

The two-window synthetic fixtures (tools/gen_fixture.py) are engineered so the three
registered strategies span the fraction-gate "survives a window" rule (>=MIN_TRADED_DAYS
traded, a strict >50% PASS majority, AND 0 KILL):

  or_fade_long       -> 3/3 PASS in BOTH windows  -> survives both -> carried_forward.
  orb_long_5m        -> 3/3 PASS in decide (survives), but only 1/3 PASS (0 KILL) in the
                        holdout -> dropped by the fraction gate (carried_forward False).
                        The regression case the old ">=1 PASS" rule got wrong: >=1 holdout
                        PASS, no KILL, yet NOT carried.
  vwap_reclaim_long  -> never PASSes -> never a majority (the floor / 0-PASS case).

There is NO tournament winner / validation verdict — only the per-strategy flag.
"""

import json

from same_day_lab import cli, runner
from same_day_lab.config import load_config
from same_day_lab.reports.tournament import (
    MIN_TRADED_DAYS,
    SURVIVE_PASS_FRACTION,
    SURVIVES_RULE,
    _survives,
)
from same_day_lab.storage import sqlite as db
from same_day_lab.strategy import STRATEGIES

DECIDE = ("2025-08-04", "2025-08-13")
HOLDOUT = ("2025-08-18", "2025-08-27")
INGEST_DATES = [
    # decide window: 3 orb-survive + 3 or-fade-survive (08-12/08-13 left open)
    "2025-08-04", "2025-08-05", "2025-08-06", "2025-08-07", "2025-08-08", "2025-08-11",
    # holdout window: 3 or-fade-survive + 1 orb-survive + 2 orb-holdmore (08-26/08-27 open)
    "2025-08-18", "2025-08-19", "2025-08-20", "2025-08-21", "2025-08-22", "2025-08-25",
]

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

    # Pin the v0.4b.1 fraction gate: orb is dropped by the holdout *fraction*, NOT a KILL —
    # it has >=1 surviving holdout day yet is not a strict majority, the exact case the old
    # ">=1 PASS AND 0 KILL" rule wrongly carried forward.
    orb_hold = _row(t, "orb_long_5m")["holdout"]
    assert orb_hold["days_traded"] == 3
    assert orb_hold["survived_pass"] == 1      # >=1 PASS ...
    assert orb_hold["killed"] == 0             # ... and 0 KILL ...
    assert 0 < orb_hold["survived_pass"] / orb_hold["days_traded"] <= SURVIVE_PASS_FRACTION
    # The carried strategy clears by a real majority over the day floor (not a lone PASS).
    for window in ("decide", "holdout"):
        carried_win = _row(t, "or_fade_long")[window]
        assert carried_win["days_traded"] >= MIN_TRADED_DAYS
        assert carried_win["survived_pass"] == 3
        assert carried_win["killed"] == 0
    assert _row(t, "orb_long_5m")["decide"]["survived_pass"] == 3


def test_multiple_comparisons_caveat_states_N(tmp_path):
    t = _tournament(tmp_path)
    caveat = t["multiple_comparisons_caveat"]
    assert str(t["n_strategies"]) in caveat  # N stated explicitly
    assert "holdout" in caveat.lower()
    assert "weak" in caveat.lower()


def test_survives_rule_is_stated(tmp_path):
    t = _tournament(tmp_path)
    rule = t["survives_rule"]
    assert rule == SURVIVES_RULE
    assert "PASS_FOR_MORE_TESTING" in rule
    assert "KILL_STRATEGY" in rule
    # The fraction gate must state its a-priori constants: the day floor and the >50% majority.
    assert str(MIN_TRADED_DAYS) in rule
    assert ">50%" in rule


def test_survives_is_majority_with_floor_and_kill_gate():
    """The fraction gate, exercised directly (no fixtures): every clause, and the strict
    >50% boundary, independently of how any synthetic day happens to fill the counts."""
    def counts(traded, survived, killed=0):
        return {
            "traded": traded,
            "traded_survived_pass_threshold": survived,
            "traded_killed_by_friction": killed,
        }

    assert MIN_TRADED_DAYS == 3 and SURVIVE_PASS_FRACTION == 0.50  # pre-stated constants
    # Day floor: too few traded days can't corroborate, even at 100% PASS.
    assert _survives(counts(2, 2)) is False
    # KILL clause: any fill-honesty KILL kills survival, even with a PASS majority.
    assert _survives(counts(3, 3, killed=1)) is False
    # Strict majority: exactly 50% is NOT a majority (the comparison is `>`, not `>=`).
    assert _survives(counts(4, 2)) is False
    # A strict majority over the floor survives.
    assert _survives(counts(3, 2)) is True
    assert _survives(counts(3, 3)) is True
    # The real regression: 1 of 7 surviving days, 0 KILL — the old rule carried this; the
    # fraction gate drops it.
    assert _survives(counts(7, 1)) is False


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
    # Decide ingested 08-04..08-11 -> 08-12/08-13 left open; weekends not listed.
    assert t["decide_window"]["missing_weekdays"] == ["2025-08-12", "2025-08-13"]
    # Holdout ingested 08-18..08-25 -> 08-26/08-27 left open.
    assert t["holdout_window"]["missing_weekdays"] == ["2025-08-26", "2025-08-27"]


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
