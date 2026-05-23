"""Archive the verbatim provider/fixture payload to disk before normalization.

The raw archive is the lab's source of truth: every run can reconstruct exactly
what the system ingested, and the stored ``raw_hash`` lets later steps verify the
payload was not altered.
"""

import json
import os
from datetime import datetime, timezone

from ..hashing import content_hash


def archive_raw(
    raw_payload,
    *,
    provider: str,
    symbol: str,
    date: str,
    request_params: dict,
    config_hash: str,
    raw_dir: str,
) -> dict:
    """Wrap, hash, and persist a raw payload; return the wrapper plus its path.

    ``raw_hash`` is computed over the payload only (before wrapping). The
    ``ingest_run_id`` is deterministic per (provider, symbol, date) so that
    re-ingesting the same day overwrites rather than accumulating duplicates.
    """
    raw_hash = content_hash(raw_payload)
    ingest_run_id = f"{provider}_{symbol}_{date}"
    wrapper = {
        "ingest_run_id": ingest_run_id,
        "provider": provider,
        "symbol": symbol,
        "date": date,
        "request_params": request_params,
        "fetch_ts_utc": datetime.now(timezone.utc).isoformat(),
        "config_hash": config_hash,
        "raw_payload": raw_payload,
        "raw_hash": raw_hash,
    }

    os.makedirs(raw_dir, exist_ok=True)
    path = os.path.join(raw_dir, f"{ingest_run_id}.json")
    with open(path, "w") as f:
        json.dump(wrapper, f, indent=2)

    return {**wrapper, "path": path}
