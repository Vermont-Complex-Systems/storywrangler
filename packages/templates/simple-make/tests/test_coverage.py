"""
Entity coverage tests — confirm all entity values in the data
have mappings in config/entities.yaml.

Adapt the queries to your storage format and entity column name.
"""

import pytest


@pytest.mark.skip(reason="Implement query for your storage and entity column")
def test_all_entities_have_mappings(db, expected_entities):
    """Every distinct entity value in the data must appear in entities.yaml."""
    # Replace with your table name and entity column:
    rows = db.execute("SELECT DISTINCT geo FROM my_table ORDER BY geo").fetchall()
    data_entities = {r[0] for r in rows}
    missing = data_entities - set(expected_entities)

    assert not missing, (
        f"{len(missing)} value(s) in data have no entity mapping:\n"
        + "\n".join(f"  - {e}" for e in sorted(missing))
    )


@pytest.mark.skip(reason="Implement query for your storage and entity column")
def test_no_null_entities(db):
    """Entity column must not contain nulls."""
    # Replace with your table name and entity column:
    (null_count,) = db.execute("SELECT COUNT(*) FROM my_table WHERE geo IS NULL").fetchone()
    assert null_count == 0, f"Found {null_count} rows with NULL entity value"
