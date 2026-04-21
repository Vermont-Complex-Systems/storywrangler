"""
Test fixtures for backend query utilities.

Uses in-memory DuckDB with sample data — no PostgreSQL, no async, no FastAPI TestClient.
Tests can run with just `pytest backend/tests/`.
"""
import os
import shutil
import tempfile
from types import SimpleNamespace

import duckdb
import pytest


@pytest.fixture
def conn():
    """In-memory DuckDB connection, closed after test."""
    c = duckdb.connect()
    yield c
    c.close()


@pytest.fixture
def sample_parquet(conn, tmp_path):
    """Write a sample flat parquet file mimicking field-venue-metrics.

    Schema: field (VARCHAR), year (INTEGER), venue (VARCHAR),
            metric_type (VARCHAR), count (INTEGER)
    """
    parquet_path = str(tmp_path / "metrics.parquet")
    conn.execute(f"""
        COPY (
            SELECT * FROM (VALUES
                ('Computer Science', 2020, 'Nature',  'total',        100),
                ('Computer Science', 2020, 'Nature',  'has_abstract',  80),
                ('Computer Science', 2020, 'Science', 'total',         60),
                ('Computer Science', 2020, 'Science', 'has_abstract',  50),
                ('Computer Science', 2021, 'Nature',  'total',        120),
                ('Computer Science', 2021, 'Nature',  'has_abstract',  90),
                ('Computer Science', 2021, 'Science', 'total',         70),
                ('Computer Science', 2021, 'Science', 'has_abstract',  55),
                ('Physics',          2020, 'Nature',  'total',         90),
                ('Physics',          2020, 'Nature',  'has_abstract',  70),
                ('Physics',          2021, 'Nature',  'total',        110),
                ('Physics',          2021, 'Nature',  'has_abstract',  85)
            ) AS t(field, year, venue, metric_type, count)
        ) TO '{parquet_path}' (FORMAT PARQUET)
    """)
    return parquet_path


@pytest.fixture
def sample_hive_parquet(conn, tmp_path):
    """Write hive-partitioned parquet mimicking field-venue-metrics layout.

    Structure: {root}/field=Computer Science/data.parquet
               {root}/field=Physics/data.parquet
    """
    root = str(tmp_path / "field-venue-metrics")
    conn.execute(f"""
        COPY (
            SELECT * FROM (VALUES
                ('Computer Science', 2020, 'Nature',  'total',        100),
                ('Computer Science', 2020, 'Nature',  'has_abstract',  80),
                ('Computer Science', 2020, 'Science', 'total',         60),
                ('Computer Science', 2021, 'Nature',  'total',        120),
                ('Computer Science', 2021, 'Science', 'total',         70),
                ('Physics',          2020, 'Nature',  'total',         90),
                ('Physics',          2021, 'Nature',  'total',        110)
            ) AS t(field, year, venue, metric_type, count)
        ) TO '{root}' (FORMAT PARQUET, PARTITION_BY (field))
    """)
    return root


def make_dataset_obj(
    data_location,
    data_format="parquet",
    endpoint_schema=None,
    transform=None,
    data_schema=None,
    filter_values=None,
    entity_mapping=None,
):
    """Create a SimpleNamespace mimicking a RegistryEntry for query_utils."""
    return SimpleNamespace(
        data_location=data_location,
        data_format=data_format,
        endpoint_schema=endpoint_schema or {"type": "time-series", "count_column": "count"},
        transform=transform or {
            "time_dimension": "year",
            "filter_dimensions": ["field", "venue"],
            "partition_dimensions": {"metric_type": "total"},
        },
        data_schema=data_schema or {"year": "INTEGER"},
        filter_values=filter_values or {},
        entity_mapping=entity_mapping,
    )
