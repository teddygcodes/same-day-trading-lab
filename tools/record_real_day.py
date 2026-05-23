"""Creds-gated capture of one real Alpaca IEX day into a committed offline fixture.

NOT part of the test suite (it makes a live network call). With creds set:

    export ALPACA_API_KEY=... ALPACA_SECRET_KEY=...
    python tools/record_real_day.py --symbol AAPL --date 2025-06-16

Writes a fixture-shaped JSON (same keys as fixtures/, no credentials in it) so a
real session becomes a deterministic, offline regression fixture replayable via
`same-day-lab ingest --provider fixture`.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from same_day_lab.config import load_config       # noqa: E402
from same_day_lab.ingest import alpaca             # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")


def _default_out(symbol: str, date: str) -> str:
    return os.path.join(FIXTURES, f"real_{symbol.lower()}_{date}_iex.json")


def record(symbol: str, date: str, out: str, *, config: dict | None = None) -> tuple[str, dict]:
    config = config or load_config()
    payload = alpaca.fetch_bars(symbol, date, config, feed="iex")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    return out, payload


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="record_real_day", description=__doc__)
    p.add_argument("--symbol", required=True)
    p.add_argument("--date", required=True, help="YYYY-MM-DD (a real trading day)")
    p.add_argument("--out", default=None, help="output fixture path")
    args = p.parse_args(argv)
    out = args.out or _default_out(args.symbol, args.date)
    try:
        path, payload = record(args.symbol, args.date, out)
    except (alpaca.AlpacaCredentialsMissing, alpaca.AlpacaError) as exc:
        print(f"record failed: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {path} ({len(payload['bars'])} bars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
