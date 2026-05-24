"""Load committed fixture payloads (offline provider).

``load_fixture`` resolves a requested ``(symbol, date)`` in strict priority order:
the reserved synthetic-fixture map, then a recorded real day
(``real_<symbol.lower()>_<date>_iex.json``, written by ``tools/record_real_day.py``),
otherwise it raises. It NEVER falls back to the synthetic sample — silently serving
fabricated data for a requested real date would violate the lab's provenance stance
(CLAUDE.md invariant 7).

Single-day fixtures are self-describing; if a fixture's embedded date differs from the
request we honor the fixture and record a note rather than fabricate data.
"""

import json
import os

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "fixtures"
)

# Reserved synthetic (symbol, date) -> fixture filename. These dates take precedence;
# real pulls must use other dates. No silent fallback for anything else.
_FIXTURE_FILES = {
    ("AAPL", "2025-05-15"): "sample_aapl_1m_day.json",
    ("AAPL", "2025-11-28"): "half_day_aapl_1m.json",
    ("AAPL", "2025-06-16"): "messy_real_aapl_1m.json",
    # v0.3 multi-day synthetic mix (2025-07-07 Mon .. 07-10 Thu); 07-11 left open.
    ("AAPL", "2025-07-07"): "survive_aapl_1m.json",
    ("AAPL", "2025-07-08"): "kill_aapl_1m.json",
    ("AAPL", "2025-07-09"): "nosignal_aapl_1m.json",
    ("AAPL", "2025-07-10"): "invalid_aapl_1m.json",
    # v0.4b two-window tournament mix. Decide window 2025-08-04..08-08 (ingest 08-04,
    # 08-05); holdout window 2025-08-11..08-15 (ingest 08-11, 08-12). Other weekdays
    # left open → per-window missing-weekday surfacing.
    ("AAPL", "2025-08-04"): "orb_survive_0804_aapl_1m.json",
    ("AAPL", "2025-08-05"): "or_fade_survive_0805_aapl_1m.json",
    ("AAPL", "2025-08-11"): "orb_kill_0811_aapl_1m.json",
    ("AAPL", "2025-08-12"): "or_fade_survive_0812_aapl_1m.json",
}


class FixtureNotFound(FileNotFoundError):
    """No reserved fixture maps to a requested (symbol, date) and no recorded real file exists."""


def _real_day_filename(symbol: str, date: str) -> str:
    """Recorded-real basename; must match tools/record_real_day._default_out exactly."""
    return f"real_{symbol.lower()}_{date}_iex.json"


def load_fixture(symbol: str, date: str, fixtures_dir: str | None = None) -> dict:
    base = fixtures_dir or FIXTURES_DIR
    filename = _FIXTURE_FILES.get((symbol, date))
    if filename is None:
        real = _real_day_filename(symbol, date)
        if os.path.exists(os.path.join(base, real)):
            filename = real
        else:
            raise FixtureNotFound(
                f"no fixture for {symbol} {date}; record one with "
                "tools/record_real_day.py or use a known fixture date"
            )
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
