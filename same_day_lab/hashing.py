"""Deterministic content hashing.

Hashes are computed over canonical JSON (sorted keys, tight separators) so that
logically-identical data produces identical hashes regardless of key order or
incidental whitespace. Used for raw-archive integrity, config hashing, and the
deterministic report core.
"""

import hashlib
import json


def canonical_bytes(data) -> bytes:
    """Serialize ``data`` to canonical bytes for hashing.

    Bytes pass through unchanged; everything else is dumped as canonical JSON.
    ``default=str`` lets datetimes and other simple objects serialize stably.
    """
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def content_hash(data) -> str:
    """Return the SHA-256 hex digest of ``data``'s canonical representation."""
    return hashlib.sha256(canonical_bytes(data)).hexdigest()
