"""Thin SQLite access layer.

All writes go through ``_insert``, which builds parameterized statements from
dict keys (internal column names, never user input) with ``?`` value
placeholders, so values cannot inject SQL.
"""

import os
import sqlite3

from .schema import init_db

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "same_day_lab.sqlite3",
)


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _insert(conn: sqlite3.Connection, table: str, row: dict, *, replace: bool = False) -> None:
    cols = list(row.keys())
    verb = "INSERT OR REPLACE" if replace else "INSERT"
    sql = f"{verb} INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})"
    conn.execute(sql, [row[c] for c in cols])


def insert_ingest_run(conn, row: dict) -> None:
    _insert(conn, "ingest_runs", row, replace=True)
    conn.commit()


def insert_bars(conn, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    sql = f"INSERT INTO bars ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})"
    conn.executemany(sql, [[r[c] for c in cols] for r in rows])
    conn.commit()


def delete_bars_for_ingest(conn, ingest_run_id: str) -> None:
    """Clear prior bars for a re-ingested day so counts stay correct."""
    conn.execute("DELETE FROM bars WHERE ingest_run_id = ?", (ingest_run_id,))
    conn.commit()


def upsert_session(conn, row: dict) -> None:
    _insert(conn, "sessions", row, replace=True)
    conn.commit()


def insert_run(conn, row: dict) -> None:
    _insert(conn, "runs", row, replace=True)
    conn.commit()


def insert_trade(conn, row: dict) -> None:
    _insert(conn, "trades", row, replace=True)
    conn.commit()


def get_ingest_run(conn, symbol: str, date: str):
    return conn.execute(
        "SELECT * FROM ingest_runs WHERE symbol = ? AND session_date = ?", (symbol, date)
    ).fetchone()


def get_ingest_runs_in_range(conn, symbol: str, start: str, end: str):
    """Ingested rows for ``symbol`` with ``start <= session_date <= end``.

    ``session_date`` is stored as ISO ``YYYY-MM-DD`` TEXT, so a lexicographic
    ``BETWEEN`` is also a chronological one.
    """
    return conn.execute(
        "SELECT * FROM ingest_runs WHERE symbol = ? AND session_date BETWEEN ? AND ? "
        "ORDER BY session_date",
        (symbol, start, end),
    ).fetchall()


def get_bars(conn, ingest_run_id: str):
    return conn.execute(
        "SELECT * FROM bars WHERE ingest_run_id = ? ORDER BY bar_start_ts_utc", (ingest_run_id,)
    ).fetchall()


def get_session(conn, symbol: str, date: str):
    return conn.execute(
        "SELECT * FROM sessions WHERE symbol = ? AND session_date = ?", (symbol, date)
    ).fetchone()


def latest_run(conn, symbol: str, date: str):
    return conn.execute(
        "SELECT * FROM runs WHERE symbol = ? AND session_date = ? "
        "ORDER BY completed_at_utc DESC LIMIT 1",
        (symbol, date),
    ).fetchone()


__all__ = [
    "connect",
    "init_db",
    "insert_ingest_run",
    "insert_bars",
    "delete_bars_for_ingest",
    "upsert_session",
    "insert_run",
    "insert_trade",
    "get_ingest_run",
    "get_ingest_runs_in_range",
    "get_bars",
    "get_session",
    "latest_run",
]
