"""
Storywrangler CLI — scaffold new dataset projects.

Usage:
    uvx storywrangler new <project-name> --format parquet
    uvx storywrangler new <project-name> --format parquet_hive

The generated project follows the simple-make pattern:
  extract/ → transform/ → load/ (submit) → tests/
"""

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version as _version
from importlib.resources import files as pkg_files
from pathlib import Path


def _pkg_version() -> str:
    try:
        return _version("storywrangler")
    except PackageNotFoundError:
        return "unknown"

FORMATS = ("parquet", "parquet_hive")
ORCHESTRATORS = ("make", "snakemake")

# Human-facing guidance for `storywrangler formats` and the `new` help — what
# each storage format is and when to reach for it.
FORMAT_GUIDE = {
    "parquet": (
        "Single parquet file or a flat directory of parquet files.",
        "Use for small-to-medium datasets that fit one file or one folder. "
        "data_location is the file or directory.",
    ),
    "parquet_hive": (
        "Hive-partitioned directory tree — every level named col=val/.",
        "Use for large datasets partitioned by entity, time, or other axes: "
        "DuckDB prunes partitions automatically and levels are auto-discovered "
        "at registration. data_location is the root of the tree.",
    ),
}


def _print_formats() -> None:
    """Print the storage-format guide (names + when to use each)."""
    print("Storage formats for `storywrangler new --format`:\n")
    for fmt in FORMATS:
        summary, when = FORMAT_GUIDE[fmt]
        print(f"  {fmt}")
        print(f"      {summary}")
        print(f"      {when}\n")

# Agent skills are scaffolded into new projects so Claude Code (and other
# agents) know the submission conventions and can reach the storywrangler MCP
# server. Shipped as package data under agent_assets/skills/, synced from the
# monorepo's .claude/skills by scripts/sync_agent_assets.py — discovered at
# scaffold time, never hard-coded here.


# ── Common files (format-independent) ────────────────────────

PYPROJECT = """\
[project]
name = "{name}"
version = "0.1.0"
description = "Dataset pipeline for Storywrangler"
requires-python = ">=3.11"
dependencies = [
    "duckdb>=1.4",
    "pyprojroot>=0.3.0",
    "python-dotenv>=1.0",
    "pyyaml>=6.0",
    "requests>=2.31",
    "storywrangler>=0.0.5",
]

[project.optional-dependencies]
test = ["pytest>=8.0"]
"""

ENV_EXAMPLE = """\
# Copy to .env and fill in values

DATASET_ID={name}
DOMAIN=my-domain          # must match a registered domain in the API
DATA_PATH=/path/to/data

STORYWRANGLER_URL=https://api.storywrangler.uvm.edu   # API base; use http://localhost:8000 for local dev
API_KEY=your-api-key
"""

MAKEFILE = """\
.PHONY: extract transform validate submit test

extract:
\tuv run python extract/src/scrape.py

transform:
\tuv run python transform/src/process.py

# Dry-run the registration payload through the validator before submitting.
validate:
\tuv run python load/submit.py --dry-run | uvx storywrangler-mcp validate-submission -

submit:
\tuv run python load/submit.py

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


rule validate:
    shell:
        "uv run python load/submit.py --dry-run | uvx storywrangler-mcp validate-submission -"


rule submit:
    shell:
        "uv run python load/submit.py"


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
        f"{len(missing)} value(s) in data have no entity mapping:\\n"
        + "\\n".join(f"  - {e}" for e in sorted(missing))
    )


def test_no_null_entities(db):
    \"\"\"Entity column must not contain nulls.\"\"\"
    # TODO: replace table/column names
    (null_count,) = db.execute("SELECT COUNT(*) FROM my_table WHERE geo IS NULL").fetchone()
    assert null_count == 0, f"Found {null_count} rows with NULL entity value"
"""


# ── Format-specific files ─────────────────────────────────────

SUBMIT = {

"parquet": """\
\"\"\"Load — submit the dataset to Storywrangler (parquet)\"\"\"

import json
import os
import sys
import yaml
from pathlib import Path

from pyprojroot import here
from storywrangler import Storywrangler
from dotenv import load_dotenv

load_dotenv(override=True)


def get_entities() -> list[dict]:
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f) or {}  # empty file -> no entities yet
    return [{"local_id": k, **v} for k, v in mappings.items()]


def build_payload() -> dict:
    return {
        "catalog": "vcsi",
        "dataset_id": os.getenv("DATASET_ID"),
        "domain": os.getenv("DOMAIN"),
        "data_location": str(Path(os.getenv("DATA_PATH"))),
        "data_format": "parquet",
        "description": "TODO",
        "entity_mapping": {"local_id_column": "geo"},  # TODO: adjust column name
        "entities": get_entities(),
        "endpoint_schema": {
            "type": "types-counts",
        },
        "transform": {
            "time_dimension": "year",       # TODO: adjust time column name
            # "filter_dimensions": ["sex"], # optional: non-hive columns to expose as query filters
        },
        "ownership": {"owner_group": "vcsi", "contact": "your@email.edu", "storage_risk": "institutional"},
        "lineage": {"repo": "https://github.com/your-org/your-repo", "sources": {}, "derived_from": []},
    }


def main():
    payload = build_payload()
    # `--dry-run` prints the payload as JSON and skips registration, so you can
    # validate it before submitting (see `make validate`):
    #   uv run python load/submit.py --dry-run | uvx storywrangler-mcp validate-submission -
    if "--dry-run" in sys.argv:
        print(json.dumps(payload))
        return
    client = Storywrangler()  # reads API_KEY (and optionally STORYWRANGLER_URL) from .env
    name = payload["dataset_id"]
    success = client.registry.register(payload)
    print(f"\\n{name} registered" if success else "\\nRegistration failed")


if __name__ == "__main__":
    main()
""",

"parquet_hive": """\
\"\"\"Load — submit the dataset to Storywrangler (parquet_hive)

Hive partition levels are auto-discovered from the directory structure.
You only need to declare time_dimension and (optionally) hash_bucket.
Availability is auto-computed by the server at registration time.

If your dataset uses hash buckets, use assign_bucket() in your transform
step to partition files consistently with the query layer:

    from storywrangler.hashing import assign_bucket
    bucket = assign_bucket(term, num_buckets=16)
\"\"\"

import json
import os
import sys
import yaml
from pathlib import Path

from pyprojroot import here
from storywrangler import Storywrangler
from dotenv import load_dotenv

load_dotenv(override=True)


def get_entities() -> list[dict]:
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f) or {}  # empty file -> no entities yet
    return [{"local_id": k, **v} for k, v in mappings.items()]


def build_payload() -> dict:
    return {
        "catalog": "vcsi",
        "dataset_id": os.getenv("DATASET_ID"),
        "domain": os.getenv("DOMAIN"),
        "data_location": str(Path(os.getenv("DATA_PATH"))),
        "data_format": "parquet_hive",
        "description": "TODO",
        "entity_mapping": {"local_id_column": "geo"},  # TODO: adjust column name
        "entities": get_entities(),
        "endpoint_schema": {
            "type": "types-counts",
        },
        "transform": {
            "time_dimension": "date",               # hive partition column for time
            # "filter_dimensions": ["sex"],          # optional: non-hive columns inside parquet files
            # "time_partitions": ["year", "month"],  # optional: if time is split across hive levels
            # "hash_bucket": "ngram_bucket",         # optional: content-sharded partition column
        },
        "ownership": {"owner_group": "vcsi", "contact": "your@email.edu", "storage_risk": "institutional"},
        "lineage": {"repo": "https://github.com/your-org/your-repo", "sources": {}, "derived_from": []},
    }


def main():
    payload = build_payload()
    # `--dry-run` prints the payload as JSON and skips registration, so you can
    # validate it before submitting (see `make validate`):
    #   uv run python load/submit.py --dry-run | uvx storywrangler-mcp validate-submission -
    if "--dry-run" in sys.argv:
        print(json.dumps(payload))
        return
    client = Storywrangler()  # reads API_KEY (and optionally STORYWRANGLER_URL) from .env
    name = payload["dataset_id"]
    success = client.registry.register(payload)
    print(f"\\n{name} registered" if success else "\\nRegistration failed")


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

def scaffold_agent_assets(root: Path) -> None:
    """Write .mcp.json and .claude/skills/ into the new project.

    Best-effort: a missing asset (e.g. a stripped-down install) warns instead
    of failing the scaffold.
    """
    try:
        assets = pkg_files("storywrangler") / "agent_assets"
        (root / ".mcp.json").write_text((assets / "mcp.json").read_text())
        for entry in (assets / "skills").iterdir():
            skill_md = (entry / "SKILL.md").read_text()
            skill_dir = root / ".claude" / "skills" / entry.name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(skill_md)
    except (FileNotFoundError, OSError) as exc:
        print(f"Warning: could not scaffold agent assets ({exc})", file=sys.stderr)


def scaffold(name: str, fmt: str, orch: str):
    root = Path(name)
    # `name` may be a path (absolute or relative); the package/dataset name is
    # its final component, which must be a valid identifier.
    pkg_name = root.name
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
        root / "load",
        root / "tests",
    ]
    if orch == "snakemake":
        dirs += [root / "logs", root / "sentinels"]
    for d in dirs:
        d.mkdir(parents=True)

    files = {
        "pyproject.toml":           PYPROJECT.format(name=pkg_name),
        ".env.example":             ENV_EXAMPLE.format(name=pkg_name),
        "config/entities.yaml":     ENTITIES_YAML,
        "extract/src/scrape.py":    SCRAPE_PY,
        "transform/src/process.py": PROCESS_PY,
        "load/submit.py":        SUBMIT[fmt],
        "tests/conftest.py":        CONFTEST[fmt],
        "tests/test_coverage.py":   TEST_COVERAGE,
    }

    if orch == "make":
        files["Makefile"] = MAKEFILE
        validate_cmd, run_cmd = "make validate", "make submit"
    else:
        files["Snakefile"] = SNAKEFILE
        files["config/config.yaml"] = SNAKEMAKE_CONFIG.format(name=pkg_name)
        validate_cmd, run_cmd = "snakemake validate", "snakemake submit"

    for path, content in files.items():
        (root / path).write_text(content)

    scaffold_agent_assets(root)

    print(f"Created '{name}/' with format={fmt}, orchestrator={orch}")
    print()
    print("Next steps:")
    print(f"  cd {name}")
    print(f"  cp .env.example .env   # fill in DATASET_ID, DOMAIN, DATA_PATH, API_KEY")
    print(f"  uv sync")
    print(f"  # Edit config/entities.yaml, load/submit.py")
    print(f"  {validate_cmd}   # dry-run the payload through the validator first")
    print(f"  {run_cmd}")
    print()
    print("Agent setup: .mcp.json and .claude/skills/ were scaffolded — Claude Code")
    print("sessions in this project get the storywrangler MCP server and the")
    print("submission/querying skills automatically.")


def main():
    parser = argparse.ArgumentParser(
        prog="storywrangler",
        description="Storywrangler CLI",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"storywrangler {_pkg_version()}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("formats", help="List the storage formats and when to use each")

    new_cmd = subparsers.add_parser(
        "new",
        help="Scaffold a new dataset project",
        epilog="Run `storywrangler formats` to see what each --format means.",
    )
    new_cmd.add_argument("name", help="Project directory name")
    # Not required: when omitted we print the format guide rather than a terse
    # argparse error, so the choice is discoverable at the point of need.
    new_cmd.add_argument(
        "--format", "-f",
        choices=FORMATS,
        help="Storage format. Run `storywrangler formats` for guidance.",
    )
    new_cmd.add_argument(
        "--orchestrator", "-o",
        choices=ORCHESTRATORS,
        default="make",
        help="Pipeline orchestrator: make (default) | snakemake",
    )

    args = parser.parse_args()
    if args.command == "formats":
        _print_formats()
    elif args.command == "new":
        if args.format is None:
            print("Choose a storage format with --format.\n", file=sys.stderr)
            _print_formats()
            sys.exit(2)
        scaffold(args.name, args.format, args.orchestrator)


if __name__ == "__main__":
    main()
