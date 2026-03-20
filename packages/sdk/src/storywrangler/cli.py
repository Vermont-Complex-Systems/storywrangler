"""
Storywrangler CLI — scaffold new dataset projects.

Usage:
    uvx storywrangler new <project-name> --format ducklake
    uvx storywrangler new <project-name> --format parquet_hive
    uvx storywrangler new <project-name> --format duckdb

The generated project follows the simple-make pattern:
  extract/ → transform/ → adapter/ (prepare + submit) → tests/
"""

import argparse
import sys
from pathlib import Path

FORMATS = ("ducklake", "parquet_hive", "duckdb")
ORCHESTRATORS = ("make", "snakemake")


# ── Common files (format-independent) ────────────────────────

PYPROJECT = """\
[project]
name = "{name}"
version = "0.1.0"
description = "Dataset adapter for Storywrangler"
requires-python = ">=3.11"
dependencies = [
    "duckdb>=1.4",
    "pyprojroot>=0.3.0",
    "python-dotenv>=1.0",
    "pyyaml>=6.0",
    "requests>=2.31",
    "storywrangler-sdk",
]

[project.optional-dependencies]
test = ["pytest>=8.0"]

[tool.uv.sources]
storywrangler-sdk = {{ path = "../storywrangler/packages/sdk", editable = true }}
"""

ENV_EXAMPLE = """\
# Copy to .env and fill in values

DATASET_ID={name}
DOMAIN=my-domain          # must match a registered domain in the API
DATA_PATH=/path/to/data

API_URL=http://localhost:8000
API_KEY=your-api-key
"""

MAKEFILE = """\
.PHONY: extract transform submit test

extract:
\tuv run python extract/src/scrape.py

transform:
\tuv run python transform/src/process.py

submit:
\tuv run python adapter/submit.py

test:
\tuv run pytest tests/
"""

SNAKEFILE = """\
configfile: "config/config.yaml"

DATA_PATH = config["data_path"]


localrules: all, submit, test


rule all:
    input:
        "sentinels/transform.done",


rule extract:
    output:
        sentinel="sentinels/extract.done",
    log:
        "logs/extract.log",
    shell:
        \"\"\"
        uv run python extract/src/scrape.py 2>&1 | tee {log}
        mkdir -p sentinels && touch {output.sentinel}
        \"\"\"


rule transform:
    input:
        "sentinels/extract.done",
    output:
        sentinel="sentinels/transform.done",
    log:
        "logs/transform.log",
    shell:
        \"\"\"
        uv run python transform/src/process.py 2>&1 | tee {log}
        touch {output.sentinel}
        \"\"\"


rule submit:
    shell:
        "uv run python adapter/submit.py"


rule test:
    shell:
        "uv run pytest tests/"
"""

SNAKEMAKE_CONFIG = """\
# Snakemake configuration for {name}
# Adjust paths and settings for your environment.

data_path: /path/to/data   # TODO: set your data output path
"""

ENTITIES_YAML = """\
# Entity mappings: local_id → canonical Storywrangler entity
#
# local_id:    value in your data's entity column (e.g. geo, country)
# entity_id:   canonical ID, e.g. "wikidata:Q30" for the United States
# entity_name: human-readable label
# entity_ids:  optional alternate identifiers
#
# Example:
#
# united_states:
#   entity_id: "wikidata:Q30"
#   entity_name: "United States"
#   entity_ids:
#     - "iso:US"
"""

SCRAPE_PY = """\
\"\"\"Extract — download or scrape raw source data.\"\"\"


def main():
    raise NotImplementedError("Implement your extraction logic here")


if __name__ == "__main__":
    main()
"""

PROCESS_PY = """\
\"\"\"Transform — process raw data into storage format.\"\"\"


def main():
    raise NotImplementedError("Implement your transformation logic here")


if __name__ == "__main__":
    main()
"""

TEST_COVERAGE = """\
\"\"\"
Entity coverage tests — confirm all entity values in the data
have mappings in config/entities.yaml.
\"\"\"


def test_all_entities_have_mappings(db, expected_entities):
    \"\"\"Every distinct entity value in the data must appear in entities.yaml.\"\"\"
    # TODO: replace table/column names
    rows = db.execute("SELECT DISTINCT geo FROM my_table ORDER BY geo").fetchall()
    data_entities = {{r[0] for r in rows}}
    missing = data_entities - set(expected_entities)

    assert not missing, (
        f"{{len(missing)}} value(s) in data have no entity mapping:\\n"
        + "\\n".join(f"  - {{e}}" for e in sorted(missing))
    )


def test_no_null_entities(db):
    \"\"\"Entity column must not contain nulls.\"\"\"
    # TODO: replace table/column names
    (null_count,) = db.execute("SELECT COUNT(*) FROM my_table WHERE geo IS NULL").fetchone()
    assert null_count == 0, f"Found {{null_count}} rows with NULL entity value"
"""


# ── Format-specific files ─────────────────────────────────────

SUBMIT = {

"ducklake": """\
\"\"\"Adapter — Submit (ducklake)\"\"\"

import os
import yaml
from pathlib import Path

from pyprojroot import here
from storywrangler import Storywrangler
from dotenv import load_dotenv
import duckdb

load_dotenv(override=True)


def get_entities() -> list[dict]:
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f)
    return [{{"local_id": k, **v}} for k, v in mappings.items()]


def get_availability(conn, entities: list[dict]) -> dict:
    \"\"\"Compute min/max time range per entity. TODO: adapt query to your schema.\"\"\"
    local_to_entity = {{e["local_id"]: e["entity_id"] for e in entities}}
    rows = conn.execute(\"\"\"
        SELECT geo, MIN(year), MAX(year) FROM my_table GROUP BY geo
    \"\"\").fetchall()
    return {{
        "yearly": {{
            "available": {{
                local_to_entity[geo]: {{"min": mn, "max": mx}}
                for geo, mn, mx in rows if geo in local_to_entity
            }}
        }}
    }}


def get_ducklake_metadata(conn):
    \"\"\"Extract absolute file paths from ducklake metadata tables.

    df.path is relative to data_path, stored under schema_name/table_name/.
    We resolve everything to absolute paths so the API can find files
    regardless of which directory uvicorn runs from.
    \"\"\"
    raw = conn.execute(\"\"\"
        SELECT value FROM __ducklake_metadata_my_lake.ducklake_metadata WHERE key = 'data_path'
    \"\"\").fetchone()[0]
    data_path = str(Path(raw).resolve())
    rows = conn.execute(\"\"\"
        SELECT s.schema_name, t.table_name, df.path
        FROM __ducklake_metadata_my_lake.ducklake_data_file df
        JOIN __ducklake_metadata_my_lake.ducklake_table t ON df.table_id = t.table_id
        JOIN __ducklake_metadata_my_lake.ducklake_schema s ON t.schema_id = s.schema_id
        WHERE df.end_snapshot IS NULL
    \"\"\").fetchall()
    tables_metadata = {{}}
    for schema_name, table_name, rel_path in rows:
        abs_path = str(Path(data_path) / schema_name / table_name / rel_path.lstrip("/"))
        tables_metadata.setdefault(table_name, []).append(abs_path)
    return tables_metadata, data_path


def main():
    dataset_id = os.getenv("DATASET_ID")
    domain = os.getenv("DOMAIN")
    ducklake_path = here() / "metadata.ducklake"  # TODO: adjust

    conn = duckdb.connect()
    conn.execute(f"ATTACH 'ducklake:{{ducklake_path}}' AS my_lake;")
    conn.execute("USE my_lake;")

    entities = get_entities()
    tables_metadata, ducklake_data_path = get_ducklake_metadata(conn)
    availability = get_availability(conn, entities)
    conn.close()

    dataset_metadata = {{
        "catalog": "vcsi",
        "dataset_id": dataset_id,
        "domain": domain,
        "data_location": str(ducklake_path),
        "data_format": "ducklake",
        "description": "TODO",
        "format_config": {{
            "ducklake_data_path": ducklake_data_path,
            "tables_metadata": tables_metadata,
            "availability": availability,
        }},
        "entity_mapping": {{"local_id_column": "geo"}},  # TODO: adjust column name
        "entities": entities,
        "endpoint_schema": {{
            "type": "types-counts",
            "time_dimension": "year",       # TODO
            # "filter_dimensions": ["sex"], # optional
        }},
        "ownership": {{"owner_group": "vcsi", "contact": "your@email.edu", "storage_risk": "institutional"}},
        "lineage": {{"sources": {{}}, "derived_from": []}},
    }}

    client = Storywrangler()  # reads API_KEY (and optionally API_URL) from .env
    success = client.registry.register(dataset_metadata)
    print(f"\\n{{dataset_id}} registered" if success else "\\nRegistration failed")


if __name__ == "__main__":
    main()
""",

"parquet_hive": """\
\"\"\"Adapter — Submit (parquet_hive)\"\"\"

import os
import yaml
from pathlib import Path

from pyprojroot import here
from storywrangler import Storywrangler
from dotenv import load_dotenv
import duckdb

load_dotenv(override=True)


def get_entities() -> list[dict]:
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f)
    return [{{"local_id": k, **v}} for k, v in mappings.items()]


def get_availability(data_path: Path) -> dict:
    \"\"\"Compute coverage metadata from parquet files. TODO: adapt to your schema.\"\"\"
    conn = duckdb.connect()
    try:
        pq = data_path / "**" / "*.parquet"
        rows = conn.execute(f\"\"\"
            SELECT geo, MIN(date)::TEXT, MAX(date)::TEXT
            FROM read_parquet('{{pq}}', hive_partitioning=true)
            GROUP BY geo
        \"\"\").fetchall()
        return {{"daily": {{"available": {{r[0]: {{"min": r[1], "max": r[2]}} for r in rows}}}}}}
    finally:
        conn.close()


def main():
    dataset_id = os.getenv("DATASET_ID")
    domain = os.getenv("DOMAIN")
    data_path = Path(os.getenv("DATA_PATH"))

    entities = get_entities()

    dataset_metadata = {{
        "catalog": "vcsi",
        "dataset_id": dataset_id,
        "domain": domain,
        "data_location": str(data_path),
        "data_format": "parquet_hive",
        "description": "TODO",
        "format_config": {{
            "availability": get_availability(data_path),
        }},
        "entity_mapping": {{"local_id_column": "geo"}},  # TODO: adjust column name
        "entities": entities,
        "endpoint_schema": {{
            "type": "types-counts",
            "granularities": {{"daily": "date"}},  # TODO: adjust
            # "ngram_sizes": [1, 2],                # uncomment if data has {n}grams/ subdirs
        }},
        "ownership": {{"owner_group": "vcsi", "contact": "your@email.edu", "storage_risk": "institutional"}},
        "lineage": {{"sources": {{}}, "derived_from": []}},
    }}

    client = Storywrangler()  # reads API_KEY (and optionally API_URL) from .env
    success = client.registry.register(dataset_metadata)
    print(f"\\n{{dataset_id}} registered" if success else "\\nRegistration failed")


if __name__ == "__main__":
    main()
""",

"duckdb": """\
\"\"\"Adapter — Submit (duckdb)\"\"\"

import os
import yaml
from pathlib import Path

from pyprojroot import here
from storywrangler import Storywrangler
from dotenv import load_dotenv
import duckdb

load_dotenv(override=True)


def get_entities() -> list[dict]:
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f)
    return [{{"local_id": k, **v}} for k, v in mappings.items()]


def get_availability(conn) -> dict:
    \"\"\"Compute coverage metadata. TODO: adapt query to your schema.\"\"\"
    rows = conn.execute(\"\"\"
        SELECT geo, MIN(year), MAX(year) FROM my_table GROUP BY geo
    \"\"\").fetchall()
    return {{"yearly": {{"available": {{r[0]: {{"min": r[1], "max": r[2]}} for r in rows}}}}}}


def main():
    dataset_id = os.getenv("DATASET_ID")
    domain = os.getenv("DOMAIN")
    db_path = Path(os.getenv("DATA_PATH"))

    conn = duckdb.connect(str(db_path))
    entities = get_entities()
    availability = get_availability(conn)
    conn.close()

    dataset_metadata = {{
        "catalog": "vcsi",
        "dataset_id": dataset_id,
        "domain": domain,
        "data_location": str(db_path),
        "data_format": "duckdb",
        "description": "TODO",
        "format_config": {{
            "availability": availability,
        }},
        "entity_mapping": {{"local_id_column": "geo"}},  # TODO: adjust column name
        "entities": entities,
        "endpoint_schema": {{
            "type": "types-counts",
            "time_dimension": "year",       # TODO
            # "filter_dimensions": ["sex"], # optional
        }},
        "ownership": {{"owner_group": "vcsi", "contact": "your@email.edu", "storage_risk": "institutional"}},
        "lineage": {{"sources": {{}}, "derived_from": []}},
    }}

    client = Storywrangler()  # reads API_KEY (and optionally API_URL) from .env
    success = client.registry.register(dataset_metadata)
    print(f"\\n{{dataset_id}} registered" if success else "\\nRegistration failed")


if __name__ == "__main__":
    main()
""",

}


CONFTEST = {

"ducklake": """\
import pytest
import duckdb
import yaml
from pyprojroot import here


@pytest.fixture(scope="session")
def db():
    ducklake_path = here() / "metadata.ducklake"  # TODO: adjust
    con = duckdb.connect()
    con.execute(f"ATTACH 'ducklake:{ducklake_path}' AS my_lake;")
    con.execute("USE my_lake;")
    yield con
    con.close()


@pytest.fixture(scope="session")
def expected_entities():
    \"\"\"Load expected entity local_ids from entities.yaml — the source of truth.\"\"\"
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f)
    return list(mappings.keys())
""",

"parquet_hive": """\
import os
import pytest
import duckdb
import yaml
from pyprojroot import here


def pytest_addoption(parser):
    parser.addoption(
        "--data-dir",
        default=os.environ.get("DATA_PATH"),
        help="Path to Hive-partitioned parquet output",
    )


@pytest.fixture(scope="session")
def data_dir(request):
    return request.config.getoption("--data-dir")


@pytest.fixture(scope="session")
def db():
    con = duckdb.connect()
    yield con
    con.close()


@pytest.fixture(scope="session")
def expected_entities():
    \"\"\"Load expected entity local_ids from entities.yaml — the source of truth.\"\"\"
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f)
    return list(mappings.keys())
""",

"duckdb": """\
import pytest
import duckdb
import yaml
from pathlib import Path
from pyprojroot import here


@pytest.fixture(scope="session")
def db():
    import os
    db_path = Path(os.environ["DATA_PATH"])
    con = duckdb.connect(str(db_path))
    yield con
    con.close()


@pytest.fixture(scope="session")
def expected_entities():
    \"\"\"Load expected entity local_ids from entities.yaml — the source of truth.\"\"\"
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f)
    return list(mappings.keys())
""",

}


# ── Scaffold ──────────────────────────────────────────────────

def scaffold(name: str, fmt: str, orch: str):
    root = Path(name)
    if root.exists():
        print(f"Error: '{name}' already exists.", file=sys.stderr)
        sys.exit(1)

    dirs = [
        root / "config",
        root / "extract" / "src",
        root / "extract" / "input",
        root / "extract" / "hand",
        root / "transform" / "src",
        root / "transform" / "input",
        root / "transform" / "hand",
        root / "adapter",
        root / "tests",
    ]
    if orch == "snakemake":
        dirs += [root / "logs", root / "sentinels"]
    for d in dirs:
        d.mkdir(parents=True)

    files = {
        "pyproject.toml":           PYPROJECT.format(name=name),
        ".env.example":             ENV_EXAMPLE.format(name=name),
        "config/entities.yaml":     ENTITIES_YAML,
        "extract/src/scrape.py":    SCRAPE_PY,
        "transform/src/process.py": PROCESS_PY,
        "adapter/submit.py":        SUBMIT[fmt],
        "tests/conftest.py":        CONFTEST[fmt],
        "tests/test_coverage.py":   TEST_COVERAGE,
    }

    if orch == "make":
        files["Makefile"] = MAKEFILE
        run_cmd = "make submit"
    else:
        files["Snakefile"] = SNAKEFILE
        files["config/config.yaml"] = SNAKEMAKE_CONFIG.format(name=name)
        run_cmd = "snakemake submit"

    for path, content in files.items():
        (root / path).write_text(content)

    print(f"Created '{name}/' with format={fmt}, orchestrator={orch}")
    print()
    print("Next steps:")
    print(f"  cd {name}")
    print(f"  cp .env.example .env   # fill in DATASET_ID, DOMAIN, DATA_PATH, API_KEY")
    print(f"  uv sync")
    print(f"  # Edit config/entities.yaml, adapter/prepare.py, adapter/submit.py")
    print(f"  {run_cmd}")


def main():
    parser = argparse.ArgumentParser(
        prog="storywrangler",
        description="Storywrangler CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_cmd = subparsers.add_parser("new", help="Scaffold a new dataset project")
    new_cmd.add_argument("name", help="Project directory name")
    new_cmd.add_argument(
        "--format", "-f",
        choices=FORMATS,
        required=True,
        help="Storage format: ducklake | parquet_hive | duckdb",
    )
    new_cmd.add_argument(
        "--orchestrator", "-o",
        choices=ORCHESTRATORS,
        default="make",
        help="Pipeline orchestrator: make (default) | snakemake",
    )

    args = parser.parse_args()
    if args.command == "new":
        scaffold(args.name, args.format, args.orchestrator)


if __name__ == "__main__":
    main()
