"""load_fixture resolves recorded real days and never silently serves the sample.

Provenance honesty (CLAUDE.md invariant 7): a requested (symbol, date) resolves to
its known/recorded file or raises — the synthetic sample is never substituted.
"""

import json

import pytest

from same_day_lab import cli
from same_day_lab.ingest import fixture
from same_day_lab.ingest.fixture import load_fixture

# session_date -> committed synthetic fixture (the three reserved, mapped dates)
RESERVED = {
    "2025-05-15": "sample_aapl_1m_day.json",
    "2025-11-28": "half_day_aapl_1m.json",
    "2025-06-16": "messy_real_aapl_1m.json",
}


def _write(path, session_date, *, symbol="AAPL"):
    path.write_text(
        json.dumps(
            {
                "symbol": symbol,
                "session_date": session_date,
                "timeframe": "1Min",
                "feed": "iex",
                "is_half_day": False,
                "bars": [{"t": f"{session_date}T13:30:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}],
            }
        )
    )


def test_recorded_real_day_is_resolved(tmp_path):
    _write(tmp_path / "real_aapl_2025-06-13_iex.json", "2025-06-13")
    payload = load_fixture("AAPL", "2025-06-13", fixtures_dir=str(tmp_path))
    assert payload["session_date"] == "2025-06-13"
    assert "fixture_notes" not in payload  # date matches; clean resolution, no note


def test_map_takes_precedence_over_same_named_real_file(tmp_path):
    # A decoy real file for a reserved date must be ignored: the map wins.
    _write(tmp_path / "real_aapl_2025-06-16_iex.json", "DECOY")
    _write(tmp_path / "messy_real_aapl_1m.json", "2025-06-16")
    payload = load_fixture("AAPL", "2025-06-16", fixtures_dir=str(tmp_path))
    assert payload["session_date"] == "2025-06-16"


def test_unmapped_date_with_no_file_raises_not_sample(tmp_path):
    # Empty dir, unmapped date: must raise rather than serve the synthetic sample.
    with pytest.raises(fixture.FixtureNotFound) as excinfo:
        load_fixture("AAPL", "2099-01-02", fixtures_dir=str(tmp_path))
    msg = str(excinfo.value)
    assert "AAPL" in msg and "2099-01-02" in msg


def test_reserved_synthetic_dates_still_resolve():
    # Against the real committed fixtures dir, the three mapped dates resolve to their
    # own synthetic fixtures (each carries its matching embedded session_date).
    for date in RESERVED:
        payload = load_fixture("AAPL", date)
        assert payload["session_date"] == date


def test_ingest_cli_surfaces_missing_fixture_gracefully(tmp_path):
    db = str(tmp_path / "lab.sqlite3")
    assert cli.main(["init-db", "--db", db]) == 0
    # unmapped date, no recorded file in the real fixtures dir -> graceful non-zero exit
    assert cli.main(
        ["ingest", "--provider", "fixture", "--symbol", "AAPL", "--date", "2099-01-02", "--db", db]
    ) == 1
