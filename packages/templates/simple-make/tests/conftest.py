import pytest
import yaml
from pyprojroot import here


@pytest.fixture(scope="session")
def expected_entities():
    """Load expected entity local_ids from entities.yaml — the source of truth."""
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f)
    return list(mappings.keys())


# Add storage fixtures here as needed, e.g.:
#
# @pytest.fixture(scope="session")
# def db():
#     import os, duckdb
#     con = duckdb.connect()
#     yield con
#     con.close()
