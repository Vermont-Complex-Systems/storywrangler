"""
Tests for availability introspection in parquet_introspect.py.

Covers all four dataset shapes:
  1. entity + partition_dim  (wikimedia/ngrams: country × granularity)
  2. entity only             (babynames/ngrams: geo, no partition_dims)
  3. partition_dim only       (scisciDB: metric_type, no entity)
  4. global                  (no entity, no partition_dims)
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.parquet_introspect import _derive_bucket_config, introspect


def _ns(**kwargs):
    """Shorthand for SimpleNamespace."""
    return SimpleNamespace(**kwargs)


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def conn():
    c = duckdb.connect()
    yield c
    c.close()


@pytest.fixture
def hive_entity_partition(conn, tmp_path):
    """wikimedia/ngrams shape: country × granularity × date."""
    root = str(tmp_path / "wikigrams")
    conn.execute(f"""
        COPY (
            SELECT * FROM (VALUES
                ('United States', 'daily',   '2024-01-01', 'cat',  100),
                ('United States', 'daily',   '2024-06-15', 'dog',   80),
                ('United States', 'weekly',  '2024-01-07', 'cat',  700),
                ('United States', 'weekly',  '2024-06-09', 'dog',  500),
                ('Canada',        'daily',   '2024-03-01', 'cat',   50),
                ('Canada',        'daily',   '2024-09-30', 'dog',   40),
                ('Canada',        'weekly',  '2024-03-04', 'cat',  350),
                ('Canada',        'weekly',  '2024-09-29', 'dog',  280)
            ) AS t(country, granularity, date, ngram, pv_count)
        ) TO '{root}' (FORMAT PARQUET, PARTITION_BY (country, granularity, date))
    """)
    return root


@pytest.fixture
def hive_entity_only(conn, tmp_path):
    """babynames shape: geo × year, no partition_dims."""
    root = str(tmp_path / "babynames")
    conn.execute(f"""
        COPY (
            SELECT * FROM (VALUES
                ('united_states', 1880, 'Mary',  100),
                ('united_states', 2022, 'Olivia', 90),
                ('quebec',        1980, 'Marie',  80),
                ('quebec',        2022, 'Emma',   70)
            ) AS t(geo, year, name, count)
        ) TO '{root}' (FORMAT PARQUET, PARTITION_BY (geo))
    """)
    return root


@pytest.fixture
def hive_partition_only(conn, tmp_path):
    """scisciDB shape: metric_type partition, no entity."""
    root = str(tmp_path / "scisci")
    conn.execute(f"""
        COPY (
            SELECT * FROM (VALUES
                ('total',        2000, 'CS',      100),
                ('total',        2024, 'Physics',  90),
                ('has_abstract', 2005, 'CS',       80),
                ('has_abstract', 2024, 'Physics',  70)
            ) AS t(metric_type, year, field, count)
        ) TO '{root}' (FORMAT PARQUET, PARTITION_BY (metric_type))
    """)
    return root


@pytest.fixture
def flat_parquet(conn, tmp_path):
    """Global shape: no entity, no partition_dims."""
    path = str(tmp_path / "global.parquet")
    conn.execute(f"""
        COPY (
            SELECT * FROM (VALUES
                (2015, 'a', 100),
                (2023, 'b',  90)
            ) AS t(year, type, count)
        ) TO '{path}' (FORMAT PARQUET)
    """)
    return path


# ── tests ─────────────────────────────────────────────────────────────────────


class TestAvailabilityEntityPartition:
    """Case 1: entity + partition_dim (wikimedia/ngrams)."""

    def test_entity_first_multi_granularity(self, conn, hive_entity_partition):
        ds = _ns(
            data_location=hive_entity_partition,
            data_format="parquet_hive",
            transform=_ns(
                time_dimension="date",
                filter_dimensions=None,
                partition_dimensions={"granularity": "daily"},
            ),
            entity_mapping=_ns(local_id_column="country"),
        )
        level_order = [
            {"column": "country", "type": "entity", "default_value": "Canada"},
            {"column": "granularity", "type": "partition", "default_value": "daily"},
            {"column": "date", "type": "time", "default_value": "2024-01-01"},
        ]
        result = introspect(conn, ds, level_order=level_order)
        avail = result["availability"]

        assert "United States" in avail
        assert "Canada" in avail

        us = avail["United States"]
        assert "daily" in us
        assert "weekly" in us
        assert us["daily"]["min"] == "2024-01-01"
        assert us["daily"]["max"] == "2024-06-15"
        assert us["weekly"]["min"] == "2024-01-07"
        assert us["weekly"]["max"] == "2024-06-09"

        ca = avail["Canada"]
        assert ca["daily"]["min"] == "2024-03-01"
        assert ca["daily"]["max"] == "2024-09-30"


class TestAvailabilityEntityOnly:
    """Case 2: entity only (babynames)."""

    def test_entity_keyed_single(self, conn, hive_entity_only):
        ds = _ns(
            data_location=hive_entity_only,
            data_format="parquet_hive",
            transform=_ns(
                time_dimension="year",
                filter_dimensions=["sex"],
                partition_dimensions=None,
            ),
            entity_mapping=_ns(local_id_column="geo"),
        )
        level_order = [
            {"column": "geo", "type": "entity", "default_value": "quebec"},
        ]
        result = introspect(conn, ds, level_order=level_order)
        avail = result["availability"]

        assert avail["united_states"] == {"min": "1880", "max": "2022"}
        assert avail["quebec"] == {"min": "1980", "max": "2022"}


class TestAvailabilityPartitionOnly:
    """Case 3: partition_dim only, no entity (scisciDB)."""

    def test_global_multi_partition(self, conn, hive_partition_only):
        ds = _ns(
            data_location=hive_partition_only,
            data_format="parquet_hive",
            transform=_ns(
                time_dimension="year",
                filter_dimensions=["field"],
                partition_dimensions={"metric_type": "total"},
            ),
            entity_mapping=None,
        )
        level_order = [
            {"column": "metric_type", "type": "partition", "default_value": "total"},
        ]
        result = introspect(conn, ds, level_order=level_order)
        avail = result["availability"]

        assert avail["total"] == {"min": "2000", "max": "2024"}
        assert avail["has_abstract"] == {"min": "2005", "max": "2024"}


class TestAvailabilityGlobal:
    """Case 4: no entity, no partition_dims."""

    def test_global_single(self, conn, flat_parquet):
        ds = _ns(
            data_location=flat_parquet,
            data_format="parquet",
            transform=_ns(
                time_dimension="year",
                filter_dimensions=None,
                partition_dimensions=None,
            ),
            entity_mapping=None,
        )
        result = introspect(conn, ds)
        avail = result["availability"]

        assert avail == {"min": "2015", "max": "2023"}


class TestAvailabilityTimeDimensionTypes:
    """Verify MIN/MAX works across different time column types."""

    def test_timestamp_column(self, conn, tmp_path):
        """TIMESTAMP time_dimension casts to text correctly."""
        path = str(tmp_path / "ts.parquet")
        conn.execute(f"""
            COPY (
                SELECT * FROM (VALUES
                    (TIMESTAMP '2024-01-01 08:30:00', 'a', 10),
                    (TIMESTAMP '2024-12-31 23:59:59', 'b', 20)
                ) AS t(ts, type, count)
            ) TO '{path}' (FORMAT PARQUET)
        """)
        ds = _ns(
            data_location=path,
            data_format="parquet",
            transform=_ns(
                time_dimension="ts",
                filter_dimensions=None,
                partition_dimensions=None,
            ),
            entity_mapping=None,
        )
        result = introspect(conn, ds)
        avail = result["availability"]
        assert avail["min"] == "2024-01-01 08:30:00"
        assert avail["max"] == "2024-12-31 23:59:59"

    def test_integer_year_column(self, conn, flat_parquet):
        """INTEGER year column casts to text correctly."""
        ds = _ns(
            data_location=flat_parquet,
            data_format="parquet",
            transform=_ns(
                time_dimension="year",
                filter_dimensions=None,
                partition_dimensions=None,
            ),
            entity_mapping=None,
        )
        result = introspect(conn, ds)
        avail = result["availability"]
        assert avail == {"min": "2015", "max": "2023"}


class TestAvailabilityNoTimeDimension:
    """Availability should be absent when time_dimension is not set."""

    def test_no_availability_without_time(self, conn, flat_parquet):
        ds = _ns(
            data_location=flat_parquet,
            data_format="parquet",
            transform=_ns(
                time_dimension=None,
                filter_dimensions=None,
                partition_dimensions=None,
            ),
            entity_mapping=None,
        )
        result = introspect(conn, ds)
        assert "availability" not in result

    def test_no_availability_without_transform(self, conn, flat_parquet):
        ds = _ns(
            data_location=flat_parquet,
            data_format="parquet",
            transform=None,
            entity_mapping=None,
        )
        result = introspect(conn, ds)
        assert "availability" not in result


# ── bucket config derivation ─────────────────────────────────────────────────


class TestDeriveBucketConfig:
    """Tests for _derive_bucket_config() — auto-discovering bucket counts."""

    def test_uniform_buckets(self, tmp_path):
        """All entities × partitions have the same bucket count → no overrides."""
        root = tmp_path / "data"
        for n in [1, 2]:
            for country in ["US", "CA"]:
                for b in range(4):
                    d = root / f"ngram_size={n}" / f"country={country}" / f"bucket={b}"
                    d.mkdir(parents=True)
                    (d / "data.parquet").touch()

        level_order = [
            {"column": "ngram_size", "type": "partition", "default_value": 1},
            {"column": "country", "type": "entity", "default_value": "CA"},
            {"column": "bucket", "type": "hash_bucket", "default_value": 0},
        ]
        config = _derive_bucket_config(str(root), level_order)
        assert config["column"] == "bucket"
        assert config["default_count"] == 4
        assert "overrides" not in config

    def test_per_entity_overrides(self, tmp_path):
        """Different bucket counts per entity × partition → overrides populated."""
        root = tmp_path / "data"
        # ngram_size=1: US gets 8 buckets, CA gets 4
        for b in range(8):
            d = root / "ngram_size=1" / "country=US" / f"bucket={b}"
            d.mkdir(parents=True)
            (d / "data.parquet").touch()
        for b in range(4):
            d = root / "ngram_size=1" / "country=CA" / f"bucket={b}"
            d.mkdir(parents=True)
            (d / "data.parquet").touch()
        # ngram_size=2: US gets 16 buckets, CA gets 4
        for b in range(16):
            d = root / "ngram_size=2" / "country=US" / f"bucket={b}"
            d.mkdir(parents=True)
            (d / "data.parquet").touch()
        for b in range(4):
            d = root / "ngram_size=2" / "country=CA" / f"bucket={b}"
            d.mkdir(parents=True)
            (d / "data.parquet").touch()

        level_order = [
            {"column": "ngram_size", "type": "partition", "default_value": 1},
            {"column": "country", "type": "entity", "default_value": "CA"},
            {"column": "bucket", "type": "hash_bucket", "default_value": 0},
        ]
        config = _derive_bucket_config(str(root), level_order)
        assert config["column"] == "bucket"
        # default_count is the mode — 4 appears 2 times (CA×1, CA×2)
        assert config["default_count"] == 4
        assert "US" in config["overrides"]
        assert config["overrides"]["US"]["1"] == 8
        assert config["overrides"]["US"]["2"] == 16
        # CA matches default, so no override entry
        assert "CA" not in config["overrides"]

    def test_no_hash_bucket_level(self, tmp_path):
        """No hash_bucket type in level_order → returns None."""
        root = tmp_path / "data"
        (root / "field=CS").mkdir(parents=True)

        level_order = [
            {"column": "field", "type": "partition", "default_value": "CS"},
        ]
        assert _derive_bucket_config(str(root), level_order) is None
