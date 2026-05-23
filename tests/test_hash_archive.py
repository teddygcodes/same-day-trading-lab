import json

from same_day_lab.hashing import content_hash
from same_day_lab.ingest.raw_archive import archive_raw


def test_raw_hash_roundtrip(tmp_path):
    payload = {"symbol": "AAPL", "bars": [{"t": "2025-05-15T13:30:00Z", "o": 100.0}]}
    res = archive_raw(
        payload,
        provider="fixture",
        symbol="AAPL",
        date="2025-05-15",
        request_params={"feed": "fixture"},
        config_hash="cfg123",
        raw_dir=str(tmp_path),
    )
    on_disk = json.loads((tmp_path / f"{res['ingest_run_id']}.json").read_text())
    assert on_disk["raw_hash"] == res["raw_hash"]
    assert content_hash(on_disk["raw_payload"]) == res["raw_hash"]
    assert res["ingest_run_id"] == "fixture_AAPL_2025-05-15"
    assert res["path"].endswith("fixture_AAPL_2025-05-15.json")


def test_content_hash_is_stable_and_sensitive():
    payload = {"symbol": "AAPL", "bars": [{"t": "2025-05-15T13:30:00Z", "o": 100.0}]}
    assert content_hash(payload) == content_hash(payload)
    # key order does not change the canonical hash
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})
    # content change does
    assert content_hash(payload) != content_hash({"symbol": "AAPL", "bars": []})
