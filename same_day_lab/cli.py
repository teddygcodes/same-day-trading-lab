"""Command-line entry point.

Subcommands: init-db, ingest, run, reconstruct, report. This module only parses
arguments and dispatches to the pipeline modules.
"""

import argparse
import sys

from .storage import sqlite as db


def _cmd_init_db(args) -> int:
    conn = db.connect(args.db)
    db.init_db(conn)
    print(f"initialized schema at {args.db or db.DEFAULT_DB_PATH}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="same-day-lab", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="create the SQLite schema")
    p_init.add_argument("--db", default=None, help="path to the SQLite file")
    p_init.set_defaults(func=_cmd_init_db)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
