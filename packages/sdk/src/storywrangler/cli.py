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
.PHONY: extract transform prepare submit test

extract:
\tuv run python extract/src/scrape.py

transform:
\tuv run python transform/src/process.py

prepare:
\tuv run python adapter/prepare.py

submit:
\tuv run python adapter/submit.py

test:
\tuv run pytest tests/
"""

SNAKEFILE = """\
configfile: "config/config.yaml"

DATA_PATH = config["data_path"]


localrules: all, prepare, submit, test


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


rule prepare:
    shell:
        "uv run python adapter/prepare.py"


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

PREPARE = {

"ducklake": """\
\"\"\"
Adapter — Prepare (ducklake)

Validates entity IDs and schema conformance before submission.
Entity coverage is tested in tests/.
\"\"\"

import os
import yaml
from pathlib import Path

from storywrangler.validation import EntityValidator, EndpointValidator
from pyprojroot import here
from dotenv import load_dotenv
import duckdb

load_dotenv(override=True)


class MyDatasetValidator:

    def __init__(self):
        self.project_root = here()
        self.dataset_id = os.getenv("DATASET_ID")
        self.entity_validator = EntityValidator()
        self.endpoint_validator = EndpointValidator()
        self.entities_path = self.project_root / "config" / "entities.yaml"
        self.ducklake_path = self.project_root / "metadata.ducklake"  # TODO: adjust

    def get_entities(self) -> list[dict]:
        with open(self.entities_path) as f:
            mappings = yaml.safe_load(f)
        return [{{"local_id": k, **v}} for k, v in mappings.items()]

    def validate_entities(self) -> list[dict]:
        entities = self.get_entities()
        for e in entities:
            if not self.entity_validator.validate(e["entity_id"]):
                raise ValueError(f"Invalid entity_id for '{{e['local_id']}}': {{e['entity_id']}}")
        print(f"Entity validation passed ({{len(entities)}} entities)")
        return entities

    def connect(self) -> duckdb.DuckDBPyConnection:
        if not self.ducklake_path.exists():
            raise FileNotFoundError(f"Ducklake not found: {{self.ducklake_path}}")
        conn = duckdb.connect()
        conn.execute(f"ATTACH 'ducklake:{{self.ducklake_path}}' AS my_lake;")
        conn.execute("USE my_lake;")
        return conn

    def validate_schema(self, conn: duckdb.DuckDBPyConnection):
        schema_result = conn.execute("DESCRIBE my_table").fetchall()  # TODO: table name
        columns = {{row[0]: {{"type": row[1]}} for row in schema_result}}
        validation = self.endpoint_validator.validate_types_counts_schema({{"columns": columns}})
        if not validation["valid"]:
            for error in validation["errors"]:
                print(f"  - {{error}}")
            raise ValueError("Schema does not conform to endpoint requirements")
        print("Schema validation passed")

    def validate(self):
        \"\"\"Validate entity IDs and schema conformance.\"\"\"
        print(f"Validating {{self.dataset_id}}\\n")
        self.validate_entities()
        conn = self.connect()
        try:
            self.validate_schema(conn)
            print("\\nValidation complete")
        finally:
            conn.close()


def main():
    validator = MyDatasetValidator()
    print(f"  Dataset ID: {{validator.dataset_id}}")
    print(f"  Ducklake:   {{validator.ducklake_path}}")
    print(f"  Entities:   {{validator.entities_path}}\\n")
    if not validator.ducklake_path.exists():
        print(f"Ducklake not found: {{validator.ducklake_path}}")
        print("Run the transform pipeline first.")
        return
    validator.validate()


if __name__ == "__main__":
    main()
""",

"parquet_hive": """\
\"\"\"
Adapter — Prepare (parquet_hive)

Validates entity IDs and schema conformance before submission.
Entity coverage is tested in tests/.
\"\"\"

import os
import yaml
from pathlib import Path

from storywrangler.validation import EntityValidator, EndpointValidator
from pyprojroot import here
from dotenv import load_dotenv
import duckdb

load_dotenv(override=True)

# Map dataset column names → Storywrangler spec column names if they differ
COLUMN_MAPPING = {{
    # "my_col": "types",
    # "my_count": "counts",
}}


class MyDatasetValidator:

    def __init__(self):
        self.project_root = here()
        self.dataset_id = os.getenv("DATASET_ID")
        self.data_path = Path(os.getenv("DATA_PATH"))
        self.entity_validator = EntityValidator()
        self.endpoint_validator = EndpointValidator()
        self.entities_path = self.project_root / "config" / "entities.yaml"

    def get_entities(self) -> list[dict]:
        with open(self.entities_path) as f:
            mappings = yaml.safe_load(f)
        return [{{"local_id": k, **v}} for k, v in mappings.items()]

    def validate_entities(self) -> list[dict]:
        entities = self.get_entities()
        for e in entities:
            if not self.entity_validator.validate(e["entity_id"]):
                raise ValueError(f"Invalid entity_id for '{{e['local_id']}}': {{e['entity_id']}}")
        print(f"Entity validation passed ({{len(entities)}} entities)")
        return entities

    def validate_schema(self, conn: duckdb.DuckDBPyConnection):
        parquet_glob = self.data_path / "**" / "*.parquet"  # TODO: adjust glob
        schema_result = conn.execute(f\"\"\"
            DESCRIBE SELECT * FROM read_parquet('{{parquet_glob}}', hive_partitioning=true)
        \"\"\").fetchall()
        columns = {{row[0]: {{"type": row[1]}} for row in schema_result}}
        remapped = {{COLUMN_MAPPING.get(col, col): info for col, info in columns.items()}}
        validation = self.endpoint_validator.validate_types_counts_schema({{"columns": remapped}})
        if not validation["valid"]:
            for error in validation["errors"]:
                print(f"  - {{error}}")
            raise ValueError("Schema does not conform to endpoint requirements")
        print("Schema validation passed")

    def validate(self):
        \"\"\"Validate entity IDs and schema conformance.\"\"\"
        print(f"Validating {{self.dataset_id}}\\n")
        self.validate_entities()
        conn = duckdb.connect()
        try:
            self.validate_schema(conn)
            print("\\nValidation complete")
        finally:
            conn.close()


def main():
    validator = MyDatasetValidator()
    print(f"  Dataset ID: {{validator.dataset_id}}")
    print(f"  Data path:  {{validator.data_path}}")
    print(f"  Entities:   {{validator.entities_path}}\\n")
    parquet_dir = validator.data_path
    if not parquet_dir.exists():
        print(f"Data not found: {{parquet_dir}}")
        print("Run the transform pipeline first.")
        return
    validator.validate()


if __name__ == "__main__":
    main()
""",

"duckdb": """\
\"\"\"
Adapter — Prepare (duckdb)

Validates entity IDs and schema conformance before submission.
Entity coverage is tested in tests/.
\"\"\"

import os
import yaml
from pathlib import Path

from storywrangler.validation import EntityValidator, EndpointValidator
from pyprojroot import here
from dotenv import load_dotenv
import duckdb

load_dotenv(override=True)


class MyDatasetValidator:

    def __init__(self):
        self.project_root = here()
        self.dataset_id = os.getenv("DATASET_ID")
        self.db_path = Path(os.getenv("DATA_PATH"))  # path to .duckdb file
        self.entity_validator = EntityValidator()
        self.endpoint_validator = EndpointValidator()
        self.entities_path = self.project_root / "config" / "entities.yaml"

    def get_entities(self) -> list[dict]:
        with open(self.entities_path) as f:
            mappings = yaml.safe_load(f)
        return [{{"local_id": k, **v}} for k, v in mappings.items()]

    def validate_entities(self) -> list[dict]:
        entities = self.get_entities()
        for e in entities:
            if not self.entity_validator.validate(e["entity_id"]):
                raise ValueError(f"Invalid entity_id for '{{e['local_id']}}': {{e['entity_id']}}")
        print(f"Entity validation passed ({{len(entities)}} entities)")
        return entities

    def validate_schema(self, conn: duckdb.DuckDBPyConnection):
        schema_result = conn.execute("DESCRIBE my_table").fetchall()  # TODO: table name
        columns = {{row[0]: {{"type": row[1]}} for row in schema_result}}
        validation = self.endpoint_validator.validate_types_counts_schema({{"columns": columns}})
        if not validation["valid"]:
            for error in validation["errors"]:
                print(f"  - {{error}}")
            raise ValueError("Schema does not conform to endpoint requirements")
        print("Schema validation passed")

    def validate(self):
        \"\"\"Validate entity IDs and schema conformance.\"\"\"
        print(f"Validating {{self.dataset_id}}\\n")
        self.validate_entities()
        conn = duckdb.connect(str(self.db_path))
        try:
            self.validate_schema(conn)
            print("\\nValidation complete")
        finally:
            conn.close()


def main():
    validator = MyDatasetValidator()
    print(f"  Dataset ID: {{validator.dataset_id}}")
    print(f"  DB path:    {{validator.db_path}}")
    print(f"  Entities:   {{validator.entities_path}}\\n")
    if not validator.db_path.exists():
        print(f"Database not found: {{validator.db_path}}")
        print("Run the transform pipeline first.")
        return
    validator.validate()


if __name__ == "__main__":
    main()
""",

}


SUBMIT = {

"ducklake": """\
\"\"\"Adapter — Submit (ducklake)\"\"\"

import os
import yaml
from pathlib import Path

from pyprojroot import here
from storywrangler.registry import register
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
    \"\"\"Extract file paths and data_path from ducklake metadata tables.\"\"\"
    data_path = conn.execute(\"\"\"
        SELECT value FROM __ducklake_metadata_my_lake.ducklake_metadata WHERE key = 'data_path'
    \"\"\").fetchone()[0]
    tables = [x[0] for x in conn.execute("SHOW tables").fetchall()]
    tables_metadata = {{}}
    for table in tables:
        rows = conn.execute(f\"\"\"
            SELECT df.path FROM __ducklake_metadata_my_lake.ducklake_data_file df
            JOIN __ducklake_metadata_my_lake.ducklake_table t ON df.table_id = t.table_id
            WHERE t.table_name = '{{table}}' AND df.end_snapshot IS NULL
        \"\"\").fetchall()
        if rows:
            tables_metadata[table] = [r[0] for r in rows]
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
    schema = {{row[0]: row[1] for row in conn.execute("DESCRIBE my_table").fetchall()}}
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
            "data_schema": schema,
            "availability": availability,
        }},
        "entity_mapping": {{"entity_type": "wikidata", "local_id_column": "geo"}},  # TODO
        "entities": entities,
        "sources": {{}},
        "endpoint_schemas": [{{
            "type": "types-counts",
            "time_dimension": "year",       # TODO
            "entity_dimensions": ["geo"],   # TODO
        }}],
        "ownership": {{"owner_group": "vcsi", "contact": "your@email.edu", "storage_risk": "institutional"}},
        "lineage": {{"derived_from": [], "produced_by": "adapter/submit.py"}},
    }}

    success = register(dataset_metadata)
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
from storywrangler.registry import register
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


def get_schema(data_path: Path) -> dict:
    conn = duckdb.connect()
    pq = data_path / "**" / "*.parquet"
    rows = conn.execute(f\"\"\"
        DESCRIBE SELECT * FROM read_parquet('{{pq}}', hive_partitioning=true)
    \"\"\").fetchall()
    conn.close()
    return {{row[0]: row[1] for row in rows}}


def get_table_files(data_path: Path) -> list[str]:
    return sorted(str(f) for f in data_path.rglob("*.parquet"))


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
            "data_schema": get_schema(data_path),
            "tables_metadata": {{"data": get_table_files(data_path)}},
            "availability": get_availability(data_path),
        }},
        "entity_mapping": {{"entity_type": "wikidata", "local_id_column": "geo"}},  # TODO
        "entities": entities,
        "sources": {{}},
        "endpoint_schemas": [{{
            "type": "types-counts",
            "time_dimension": "date",       # TODO
            "entity_dimensions": ["geo"],   # TODO
        }}],
        "ownership": {{"owner_group": "vcsi", "contact": "your@email.edu", "storage_risk": "institutional"}},
        "lineage": {{"derived_from": [], "produced_by": "adapter/submit.py"}},
    }}

    success = register(dataset_metadata)
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
from storywrangler.registry import register
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
    schema = {{row[0]: row[1] for row in conn.execute("DESCRIBE my_table").fetchall()}}
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
            "data_schema": schema,
            "availability": availability,
        }},
        "entity_mapping": {{"entity_type": "wikidata", "local_id_column": "geo"}},  # TODO
        "entities": entities,
        "sources": {{}},
        "endpoint_schemas": [{{
            "type": "types-counts",
            "time_dimension": "year",       # TODO
            "entity_dimensions": ["geo"],   # TODO
        }}],
        "ownership": {{"owner_group": "vcsi", "contact": "your@email.edu", "storage_risk": "institutional"}},
        "lineage": {{"derived_from": [], "produced_by": "adapter/submit.py"}},
    }}

    success = register(dataset_metadata)
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
        "adapter/prepare.py":       PREPARE[fmt],
        "adapter/submit.py":        SUBMIT[fmt],
        "tests/conftest.py":        CONFTEST[fmt],
        "tests/test_coverage.py":   TEST_COVERAGE,
    }

    if orch == "make":
        files["Makefile"] = MAKEFILE
        run_cmd = "make prepare && make submit"
    else:
        files["Snakefile"] = SNAKEFILE
        files["config/config.yaml"] = SNAKEMAKE_CONFIG.format(name=name)
        run_cmd = "snakemake prepare && snakemake submit"

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
