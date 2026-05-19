#!/usr/bin/env python3
"""Initialize the storylake DuckLake catalog in PostgreSQL.

storylake is the platform's freeze/archive catalog.  Frozen datasets are
created by copying from a submitter DuckLake catalog (READ_ONLY) into
storylake (platform has write access).

Usage
-----
# 1. Initialize the catalog (run once on a new machine or fresh DB)
    uv run python backend/scripts/init_storylake.py

# 2. Freeze a submitter catalog into storylake
    uv run python backend/scripts/init_storylake.py --freeze babynames

The script reads PostgreSQL credentials from backend/.env (same file the
FastAPI server uses).
"""

import argparse
import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv

# Load backend .env so we pick up POSTGRES_* vars
BACKEND_DIR = Path(__file__).parents[1]
load_dotenv(BACKEND_DIR / ".env")

PGHOST     = os.environ.get("POSTGRES_HOST", "localhost")
PGPORT     = os.environ.get("POSTGRES_PORT", "5432")
PGDB       = os.environ.get("POSTGRES_DB", "storywrangler")
PGUSER     = os.environ["POSTGRES_USER"]
PGPASSWORD = os.environ["POSTGRES_PASSWORD"]

STORYLAKE_SCHEMA = "storylake"
STORYLAKE_DATA   = str(Path.home() / "data" / "storylake")


def _pg_dsn(schema: str) -> str:
    return (
        f"ducklake:postgres:dbname={PGDB} host={PGHOST} port={PGPORT} "
        f"user={PGUSER} password={PGPASSWORD} "
        f"options=-csearch_path={schema}"
    )


def attach_storylake(conn: duckdb.DuckDBPyConnection, readonly: bool = False) -> None:
    opts = "READ_ONLY" if readonly else f"DATA_PATH '{STORYLAKE_DATA}/', AUTOMATIC_MIGRATION TRUE"
    conn.execute("LOAD ducklake;")
    conn.execute(f"ATTACH '{_pg_dsn(STORYLAKE_SCHEMA)}' AS {STORYLAKE_SCHEMA} ({opts});")


def init(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the storylake catalog schema in PostgreSQL (no-op if already exists)."""
    attach_storylake(conn)
    rows = conn.execute(
        f"SELECT name FROM (SHOW ALL TABLES) WHERE database = '{STORYLAKE_SCHEMA}' ORDER BY name"
    ).fetchall()
    tables = [r[0] for r in rows]
    print(f"storylake initialized.  Catalog tables: {tables}")


def freeze(conn: duckdb.DuckDBPyConnection, domain: str, force: bool = False) -> None:
    """Copy the live DuckLake table for *domain* into storylake as a frozen snapshot.

    Naming convention: storylake.main.<domain>
    The submitter catalog is assumed to be named <domain>_lake.
    """
    submitter_schema = f"{domain}_lake"

    # Attach storylake (writable) and the submitter catalog (read-only)
    attach_storylake(conn)
    conn.execute(
        f"ATTACH '{_pg_dsn(submitter_schema)}' AS {submitter_schema} "
        f"(READ_ONLY, AUTOMATIC_MIGRATION TRUE);"
    )

    # Check if the frozen table already exists
    existing = conn.execute(
        f"SELECT name FROM (SHOW ALL TABLES) WHERE database = '{STORYLAKE_SCHEMA}' AND name = '{domain}'"
    ).fetchone()

    if existing:
        if not force:
            print(f"Table {STORYLAKE_SCHEMA}.main.{domain} already exists — skipping.")
            print("Re-run with --force to drop and re-freeze.")
            return
        print(f"Dropping existing {STORYLAKE_SCHEMA}.main.{domain} ...")
        conn.execute(f"DROP TABLE {STORYLAKE_SCHEMA}.main.{domain};")

    print(f"Freezing {submitter_schema}.main.{domain} → {STORYLAKE_SCHEMA}.main.{domain} ...")
    conn.execute(
        f"CREATE TABLE {STORYLAKE_SCHEMA}.main.{domain} "
        f"AS SELECT * FROM {submitter_schema}.main.{domain};"
    )

    row_count = conn.execute(
        f"SELECT COUNT(*) FROM {STORYLAKE_SCHEMA}.main.{domain}"
    ).fetchone()[0]
    print(f"Done.  {row_count:,} rows frozen into storylake.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the storylake freeze/archive catalog")
    parser.add_argument(
        "--freeze",
        metavar="DOMAIN",
        help="Freeze a submitter DuckLake domain into storylake (e.g. 'babynames')",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Drop and re-freeze even if the table already exists",
    )
    args = parser.parse_args()

    conn = duckdb.connect()
    try:
        if args.freeze:
            freeze(conn, args.freeze, force=args.force)
        else:
            init(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
