"""Load committed fixture payloads (offline provider).

Single-day fixtures are self-describing; if the requested ``date`` differs from
the fixture's embedded date we honor the fixture and record a note rather than
fabricate data.
"""

import json
import os

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "fixtures"
)

# Map (symbol, date) -> fixture filename. Falls back to the sample day.
_FIXTURE_FILES = {
    ("AAPL", "2025-05-15"): "sample_aapl_1m_day.json",
    ("AAPL", "2025-11-28"): "half_day_aapl_1m.json",
    ("AAPL", "2025-06-16"): "messy_real_aapl_1m.json",
}


def load_fixture(symbol: str, date: str, fixtures_dir: str | None = None) -> dict:
    base = fixtures_dir or FIXTURES_DIR
    filename = _FIXTURE_FILES.get((symbol, date), "sample_aapl_1m_day.json")
    with open(os.path.join(base, filename)) as f:
        payload = json.load(f)
    notes = []
    if payload.get("session_date") != date:
        notes.append(
            f"requested date {date} differs from fixture date {payload.get('session_date')}; "
            "using the fixture's own date"
        )
    if notes:
        payload = {**payload, "fixture_notes": notes}
    return payload
