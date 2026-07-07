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
    """Use domain as view name; fall back to domain__dataset_id on collision.

    Replaces hyphens with underscores so the name is a valid SQL identifier
    (avoids needing to quote-escape everywhere).
    """
    domains = [r[0] for r in all_rows]
    if domains.count(domain) == 1:
        name = domain
    else:
        name = f"{domain}__{dataset_id}"
    return name.replace("-", "_")


def _parse_location(raw) -> str | list[str]:
    """Normalize data_location from PostgreSQL JSON column.

    PostgreSQL JSON comes back as a string that may be:
      - A JSON-encoded string: '"path/to/file.parquet"' → 'path/to/file.parquet'
      - A JSON-encoded array: '["/path/a.parquet", "/path/b.parquet"]' → list
      - A plain string: 'path/to/dir' → 'path/to/dir'
    """
    if isinstance(raw, str):
        parsed = json.loads(raw)
        return parsed
    return raw


def _resolve_views(
    base_name: str,
    data_format: str,
    data_location: str,
    level_order: list | None,
) -> list[tuple[str, str]]:
    """Return a list of (view_name, FROM_expression) pairs for a dataset.

    For parquet_hive with level_order (derived at registration), builds a
    fixed-depth wildcard glob — one ``/*`` per hive level — matching the
    query layer's ``_path_expr()``. This avoids DuckDB recursively walking
    the whole tree over NFS every time a view is queried.
    """

    if data_format == "parquet":
        if isinstance(data_location, list):
            quoted = ", ".join(f"'{p}'" for p in data_location)
            return [(base_name, f"read_parquet([{quoted}])")]
        return [(base_name, f"read_parquet('{data_location}')")]

    if data_format == "parquet_hive":
        if level_order:
            wildcards = "/*" * len(level_order)
            glob = f"{data_location}{wildcards}/*.parquet"
        else:
            # Pre-level_order dataset — recursive fallback (re-register to fix)
            glob = f"{data_location}/**/*.parquet"
        return [(base_name, f"read_parquet('{glob}', hive_partitioning=true)")]

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

        # Latest version per (domain, dataset_id) — the registry keeps one
        # row per version, and only the newest should back the view.
        rows = conn.execute(
            "SELECT DISTINCT ON (domain, dataset_id) "
            "       domain, dataset_id, data_format, data_location, level_order "
            "FROM reg.public.registry "
            "ORDER BY domain, dataset_id, created_at DESC"
        ).fetchall()

        print(f"Building {STORYLAKE_PATH}  ({len(rows)} registered datasets)\n")

        for domain, dataset_id, data_format, data_location_raw, level_order_raw in rows:
            level_order = json.loads(level_order_raw) if level_order_raw else None
            base = _view_name(domain, dataset_id, rows)
            data_location = _parse_location(data_location_raw)
            pairs = _resolve_views(base, data_format, data_location, level_order)

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
