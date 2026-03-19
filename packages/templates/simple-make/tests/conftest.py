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
#     import duckdb
#     from pyprojroot import here
#     ducklake_path = here() / "metadata.ducklake"
#     con = duckdb.connect()
#     con.execute(f"ATTACH 'ducklake:{ducklake_path}' AS my_lake;")
#     con.execute("USE my_lake;")
#     yield con
#     con.close()
