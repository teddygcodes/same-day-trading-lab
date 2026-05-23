import sqlite3

from same_day_lab.storage.schema import init_db


def test_init_db_creates_tables(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    init_db(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"ingest_runs", "bars", "sessions", "runs", "trades"} <= names


def test_init_db_is_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.sqlite3")
    init_db(conn)
    init_db(conn)  # second call must not raise (CREATE TABLE IF NOT EXISTS)
    count = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='bars'"
    ).fetchone()[0]
    assert count == 1
