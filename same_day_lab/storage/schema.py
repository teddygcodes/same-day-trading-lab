"""SQLite DDL for the lab's five tables.

All timestamps are stored as ISO-8601 strings with offset (UTC). Booleans are
stored as 0/1 integers. JSON blobs (quality flags, friction sweep, notes) are
stored as TEXT.
"""

import sqlite3

DDL = [
    """
    CREATE TABLE IF NOT EXISTS ingest_runs (
        ingest_run_id   TEXT PRIMARY KEY,
        provider        TEXT NOT NULL,
        symbol          TEXT NOT NULL,
        session_date    TEXT NOT NULL,
        fetch_ts_utc    TEXT NOT NULL,
        raw_path        TEXT NOT NULL,
        raw_hash        TEXT NOT NULL,
        config_hash     TEXT NOT NULL,
        source_warning  TEXT NOT NULL,
        created_at_utc  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bars (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        ingest_run_id            TEXT NOT NULL,
        symbol                   TEXT NOT NULL,
        session_date             TEXT NOT NULL,
        bar_start_ts_utc         TEXT NOT NULL,
        bar_end_ts_utc           TEXT NOT NULL,
        bar_duration_seconds     INTEGER NOT NULL,
        open                     REAL NOT NULL,
        high                     REAL NOT NULL,
        low                      REAL NOT NULL,
        close                    REAL NOT NULL,
        volume                   REAL NOT NULL,
        vwap                     REAL,
        trade_count              INTEGER,
        provider                 TEXT NOT NULL,
        feed                     TEXT,
        is_regular_market_hours  INTEGER NOT NULL,
        quality_flags_json       TEXT NOT NULL,
        raw_hash                 TEXT NOT NULL,
        config_hash              TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_date           TEXT NOT NULL,
        symbol                 TEXT NOT NULL,
        session_open_ts_utc    TEXT NOT NULL,
        session_close_ts_utc   TEXT NOT NULL,
        flatten_ts_utc         TEXT NOT NULL,
        is_half_day            INTEGER NOT NULL,
        bar_count_expected     INTEGER NOT NULL,
        bar_count_actual       INTEGER NOT NULL,
        quality_summary_json   TEXT NOT NULL,
        config_hash            TEXT NOT NULL,
        PRIMARY KEY (session_date, symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id                 TEXT PRIMARY KEY,
        ingest_run_id          TEXT NOT NULL,
        symbol                 TEXT NOT NULL,
        session_date           TEXT NOT NULL,
        strategy_name          TEXT NOT NULL,
        strategy_config_hash   TEXT NOT NULL,
        config_hash            TEXT NOT NULL,
        started_at_utc         TEXT NOT NULL,
        completed_at_utc       TEXT NOT NULL,
        report_json_path       TEXT NOT NULL,
        report_md_path         TEXT NOT NULL,
        report_hash            TEXT NOT NULL,
        verdict                TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        trade_id                  TEXT PRIMARY KEY,
        run_id                    TEXT NOT NULL,
        symbol                    TEXT NOT NULL,
        session_date              TEXT NOT NULL,
        signal_bar_ts_utc         TEXT,
        fill_bar_ts_utc           TEXT,
        exit_signal_bar_ts_utc    TEXT,
        exit_fill_bar_ts_utc      TEXT,
        opening_range_high        REAL,
        opening_range_low         REAL,
        trigger_price             REAL,
        naive_entry_price         REAL,
        naive_exit_price          REAL,
        naive_pnl                 REAL,
        pessimistic_entry_price   REAL,
        pessimistic_exit_price    REAL,
        pessimistic_pnl           REAL,
        friction_sweep_json       TEXT,
        exit_reason               TEXT,
        notes_json                TEXT
    )
    """,
]


def init_db(conn: sqlite3.Connection) -> None:
    for stmt in DDL:
        conn.execute(stmt)
    conn.commit()
