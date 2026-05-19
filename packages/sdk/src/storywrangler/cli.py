"""
Storywrangler CLI — scaffold new dataset projects.

Usage:
    uvx storywrangler new <project-name> --format parquet
    uvx storywrangler new <project-name> --format parquet_hive

The generated project follows the simple-make pattern:
  extract/ → transform/ → adapter/ (prepare + submit) → tests/
"""

import argparse
import sys
from pathlib import Path

FORMATS = ("parquet", "parquet_hive")
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

"parquet": """\
\"\"\"Adapter — Submit (parquet)\"\"\"

import os
import yaml
from pathlib import Path

from pyprojroot import here
from storywrangler import Storywrangler
from dotenv import load_dotenv

load_dotenv(override=True)


def get_entities() -> list[dict]:
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f)
    return [{{"local_id": k, **v}} for k, v in mappings.items()]


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
        "data_format": "parquet",
        "description": "TODO",
        "entity_mapping": {{"local_id_column": "geo"}},  # TODO: adjust column name
        "entities": entities,
        "endpoint_schema": {{
            "type": "types-counts",
        }},
        "transform": {{
            "time_dimension": "year",       # TODO: adjust time column name
            # "filter_dimensions": ["sex"], # optional: non-hive columns to expose as query filters
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
\"\"\"Adapter — Submit (parquet_hive)

Hive partition levels are auto-discovered from the directory structure.
You only need to declare time_dimension and (optionally) hash_bucket.
Availability is auto-computed by the server at registration time.

If your dataset uses hash buckets, use assign_bucket() in your transform
step to partition files consistently with the query layer:

    from storywrangler.hashing import assign_bucket
    bucket = assign_bucket(term, num_buckets=16)
\"\"\"

import os
import yaml
from pathlib import Path

from pyprojroot import here
from storywrangler import Storywrangler
from dotenv import load_dotenv

load_dotenv(override=True)


def get_entities() -> list[dict]:
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f)
    return [{{"local_id": k, **v}} for k, v in mappings.items()]


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
        "entity_mapping": {{"local_id_column": "geo"}},  # TODO: adjust column name
        "entities": entities,
        "endpoint_schema": {{
            "type": "types-counts",
        }},
        "transform": {{
            "time_dimension": "date",               # hive partition column for time
            # "filter_dimensions": ["sex"],          # optional: non-hive columns inside parquet files
            # "hash_bucket": "ngram_bucket",         # optional: content-sharded partition column
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

"parquet": """\
import pytest
import duckdb
import yaml
from pyprojroot import here


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
        help="Storage format: parquet | parquet_hive",
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
