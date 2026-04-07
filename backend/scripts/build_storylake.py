#!/usr/bin/env python3
"""Build storylake.duckdb — a DuckDB view-catalog for SQL exploration.

Creates one VIEW per registered dataset in ~/data/storylake.duckdb.
Views point to the actual data files; no data is copied.

    duckdb -ui ~/data/storylake.duckdb   # open in browser UI
    duckdb ~/data/storylake.duckdb       # open in terminal

Run this script whenever a new dataset is registered or paths change:

    uv run python backend/scripts/build_storylake.py

Credentials are read from backend/.env.
"""

import json
import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).parents[1]
load_dotenv(BACKEND_DIR / ".env")

PGHOST     = os.environ.get("POSTGRES_HOST", "localhost")
PGPORT     = os.environ.get("POSTGRES_PORT", "5432")
PGDB       = os.environ.get("POSTGRES_DB", "storywrangler")
PGUSER     = os.environ["POSTGRES_USER"]
PGPASSWORD = os.environ["POSTGRES_PASSWORD"]

STORYLAKE_PATH = Path.home() / "data" / "storylake.duckdb"


# ---------------------------------------------------------------------------
# Path resolution — yields (view_name, expr) pairs per dataset
# ---------------------------------------------------------------------------

def _view_name(domain: str, dataset_id: str, all_rows: list) -> str:
    """Use domain as view name; fall back to domain__dataset_id on collision."""
    domains = [r[0] for r in all_rows]
    if domains.count(domain) == 1:
        return domain
    return f"{domain}__{dataset_id}"


def _resolve_views(
    base_name: str,
    data_format: str,
    data_location: str,
    ep: dict,
) -> list[tuple[str, str]]:
    """Return a list of (view_name, FROM_expression) pairs for a dataset.

    Most datasets yield a single pair.  parquet_hive datasets with
    granularities yield one pair per granularity so that differing
    hive-partition keys don't conflict (e.g. date= vs month=).
    """

    if data_format == "parquet":
        return [(base_name, f"read_parquet('{data_location}')")]

    if data_format == "parquet_hive":
        granularities = (ep or {}).get("granularities") or {}
        if granularities:
            return [
                (
                    f"{base_name}__{gran}",
                    f"read_parquet('{data_location}/{gran}/**/*.parquet', hive_partitioning=true)",
                )
                for gran in granularities
            ]
        # No granularity split — single flat glob
        return [(base_name, f"read_parquet('{data_location}/**/*.parquet', hive_partitioning=true)")]

    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build() -> None:
    STORYLAKE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Open storylake.duckdb (creates if needed) and read the registry via postgres
    conn = duckdb.connect(str(STORYLAKE_PATH))
    try:
        conn.execute("INSTALL postgres; LOAD postgres;")
        conn.execute(
            f"ATTACH 'host={PGHOST} port={PGPORT} dbname={PGDB} "
            f"user={PGUSER} password={PGPASSWORD}' "
            f"AS reg (TYPE POSTGRES, READ_ONLY);"
        )

        rows = conn.execute(
            "SELECT domain, dataset_id, data_format, data_location, manifest, endpoint_schema "
            "FROM reg.public.registry ORDER BY domain, dataset_id"
        ).fetchall()

        print(f"Building {STORYLAKE_PATH}  ({len(rows)} registered datasets)\n")

        for domain, dataset_id, data_format, data_location, _fc_raw, ep_raw in rows:
            ep   = json.loads(ep_raw) if ep_raw else {}
            base = _view_name(domain, dataset_id, rows)
            pairs = _resolve_views(base, data_format, data_location, ep)

            if not pairs:
                print(f"  SKIP  {base:30s}  (format '{data_format}' not yet supported)")
                continue

            for view_name, expr in pairs:
                conn.execute(f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM {expr};")
                print(f"  VIEW  {view_name:30s}  ← {data_format}:{data_location}")

        print(f"\nDone.  Open with: duckdb -ui {STORYLAKE_PATH}")

    finally:
        conn.close()


if __name__ == "__main__":
    build()
