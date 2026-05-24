"""Creds-gated capture of real Alpaca IEX days across a weekday range.

Thin convenience loop over the same per-day fetch as ``record_real_day.py``. NOT
part of the test suite (it makes live network calls). With creds set:

    export ALPACA_API_KEY=... ALPACA_SECRET_KEY=...
    python tools/record_real_range.py --symbol AAPL --start 2025-07-07 --end 2025-07-18

Loops Mon–Fri in ``[start, end]`` (no market-calendar dependency — just the
Gregorian weekday). A day Alpaca returns no bars for (holiday / non-trading) is
**skipped with a note**, never an error and never a fabricated file. Afterward,
``ingest`` each written file (``--provider fixture``) and ``run-range`` over them.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from same_day_lab.config import load_config          # noqa: E402
from same_day_lab.ingest import alpaca                # noqa: E402
from same_day_lab.runner import weekdays_in_range     # noqa: E402

from record_real_day import _default_out              # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="record_real_range", description=__doc__)
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True, help="YYYY-MM-DD (inclusive)")
    p.add_argument("--end", required=True, help="YYYY-MM-DD (inclusive)")
    args = p.parse_args(argv)

    config = load_config()
    written, skipped = [], []
    for date in weekdays_in_range(args.start, args.end):
        try:
            payload = alpaca.fetch_bars(args.symbol, date, config, feed="iex")
        except alpaca.AlpacaCredentialsMissing as exc:
            print(f"record-range failed: {exc}", file=sys.stderr)
            return 1
        except alpaca.AlpacaError as exc:  # transient/other: note and keep going
            print(f"  {date}: skip ({exc})")
            skipped.append(date)
            continue
        if not payload.get("bars"):
            print(f"  {date}: skip (no bars — holiday/non-trading)")
            skipped.append(date)
            continue
        out = _default_out(args.symbol, date)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"  {date}: wrote {out} ({len(payload['bars'])} bars)")
        written.append(date)

    print(f"done: {len(written)} written, {len(skipped)} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
