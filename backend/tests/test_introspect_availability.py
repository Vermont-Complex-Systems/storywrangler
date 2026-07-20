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
                hash_bucket=None,
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
                hash_bucket=None,
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
                hash_bucket=None,
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
                hash_bucket=None,
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
                hash_bucket=None,
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
                hash_bucket=None,
            ),
            entity_mapping=None,
        )
        result = introspect(conn, ds)
        avail = result["availability"]
        assert avail == {"min": "2015", "max": "2023"}


class TestAvailabilityMultiFileBucket:
    """DuckLake-shaped buckets: several files per leaf, bounds must span all.

    Regression: the alphabetically-first file in a DuckLake bucket can be a
    single day's append — reading MIN/MAX from one file registered wildly
    wrong availability (e.g. a two-year dataset reduced to one date).
    """

    def test_min_max_spans_all_files_in_bucket(self, conn, tmp_path):
        root = tmp_path / "sparklines"
        bucket = root / "ngram_size=1" / "country=Canada" / "bucket=0"
        bucket.mkdir(parents=True)
        # Sorts first, holds a single mid-range date
        conn.execute(f"""
            COPY (SELECT DATE '2025-01-15' AS date, 'cat' AS ngram, 10 AS pv_count)
            TO '{bucket / "a-daily-append.parquet"}' (FORMAT PARQUET)
        """)
        # Sorts second, holds the true range
        conn.execute(f"""
            COPY (
                SELECT * FROM (VALUES
                    (DATE '2024-09-30', 'dog', 5),
                    (DATE '2026-07-01', 'emu', 7)
                ) AS t(date, ngram, pv_count)
            ) TO '{bucket / "b-tier-merged.parquet"}' (FORMAT PARQUET)
        """)
        ds = _ns(
            data_location=str(root),
            data_format="parquet_hive",
            transform=_ns(
                time_dimension="date",
                filter_dimensions=None,
                hash_bucket="bucket",
            ),
            entity_mapping=_ns(local_id_column="country"),
        )
        level_order = [
            {"column": "ngram_size", "type": "partition", "default_value": 1},
            {"column": "country", "type": "entity", "default_value": "Canada"},
            {"column": "bucket", "type": "hash_bucket", "default_value": 0},
        ]
        result = introspect(conn, ds, level_order=level_order)
        avail = result["availability"]
        assert avail["Canada"]["1"]["min"] == "2024-09-30"
        assert avail["Canada"]["1"]["max"] == "2026-07-01"


class TestAvailabilityNoTimeDimension:
    """Availability should be absent when time_dimension is not set."""

    def test_no_availability_without_time(self, conn, flat_parquet):
        ds = _ns(
            data_location=flat_parquet,
            data_format="parquet",
            transform=_ns(
                time_dimension=None,
                filter_dimensions=None,
                hash_bucket=None,
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


class TestAvailabilityUnreadableInFileTime:
    """Fail loud, never store a silent null.

    reddit shape: n/lang partitions with year/month time_partitions and the
    `date` column INSIDE the files. When the leaves can't be read (an NFS blip,
    reproduced here with empty leaves) the availability walk finds partitions
    but derives no bounds. It must raise rather than return an empty index the
    caller would silently accept — so introspect surfaces the reason and omits
    availability, and the registration guard then rejects the dataset with 422.

    Regression: a swallowed read failure used to store availability=null and
    report registration success, 404-ing every no-date query afterwards.
    """

    LEVEL_ORDER = [
        {"column": "n", "type": "filter", "default_value": "1"},
        {"column": "lang", "type": "filter", "default_value": "en"},
        {"column": "year", "type": "time_partition", "default_value": "2020"},
        {"column": "month", "type": "time_partition", "default_value": "1"},
    ]

    def _tree_with_empty_leaves(self, tmp_path):
        """Valid hive structure (so level_order derives) but no parquet in the
        leaves — stands in for data DuckDB cannot read."""
        root = tmp_path / "reddit"
        for year, month in (("2020", "1"), ("2021", "12")):
            (root / "n=1" / "lang=en" / f"year={year}" / f"month={month}").mkdir(parents=True)
        return str(root)

    def test_surfaces_error_and_omits_availability(self, conn, tmp_path):
        ds = _ns(
            data_location=self._tree_with_empty_leaves(tmp_path),
            data_format="parquet_hive",
            transform=_ns(
                time_dimension="date",  # inside the files, not a hive level
                filter_dimensions=["lang", "n"],
                time_partitions=["year", "month"],
                hash_bucket=None,
            ),
            entity_mapping=None,
        )
        # provided_schema skips the (would-fail) schema DESCRIBE so the
        # availability walk is what's under test.
        result = introspect(
            conn, ds,
            provided_schema={"ngram": "VARCHAR", "count": "BIGINT", "date": "DATE"},
            level_order=self.LEVEL_ORDER,
        )
        assert "availability" not in result           # never a silent null
        assert "availability" in result.get("introspect_error", "")  # reason surfaced


class TestAvailabilityTypeCounts:
    """types-counts datasets gain a `types` (vocabulary size) key per leaf.

    The count is the row count of the latest date's partition — used by
    frontends as a topN ceiling hint. Other endpoint types keep bounds-only
    leaves, and a failed count degrades to bounds-only rather than dropping
    availability.
    """

    LEVEL_ORDER = [
        {"column": "country", "type": "entity", "default_value": "Canada"},
        {"column": "granularity", "type": "partition", "default_value": "daily"},
        {"column": "date", "type": "time", "default_value": "2024-01-01"},
    ]

    @pytest.fixture
    def hive_types(self, conn, tmp_path):
        """Latest date holds 3 types, earliest holds 1 — the count must come
        from the max-date leaf, not the min leaf or the whole combo."""
        root = str(tmp_path / "wikigrams")
        conn.execute(f"""
            COPY (
                SELECT * FROM (VALUES
                    ('Canada', 'daily',  '2024-01-01', 'cat', 100),
                    ('Canada', 'daily',  '2024-06-15', 'cat',  80),
                    ('Canada', 'daily',  '2024-06-15', 'dog',  60),
                    ('Canada', 'daily',  '2024-06-15', 'emu',  40),
                    ('Canada', 'weekly', '2024-01-07', 'cat', 700),
                    ('Canada', 'weekly', '2024-06-09', 'dog', 500),
                    ('Canada', 'weekly', '2024-06-09', 'emu', 300)
                ) AS t(country, granularity, date, ngram, pv_count)
            ) TO '{root}' (FORMAT PARQUET, PARTITION_BY (country, granularity, date))
        """)
        return root

    def _dataset(self, root, endpoint_schema):
        return _ns(
            data_location=root,
            data_format="parquet_hive",
            transform=_ns(
                time_dimension="date",
                filter_dimensions=None,
                hash_bucket=None,
            ),
            entity_mapping=_ns(local_id_column="country"),
            endpoint_schema=endpoint_schema,
        )

    def test_leaf_gains_vocab_size_from_max_date(self, conn, hive_types):
        ds = self._dataset(
            hive_types,
            _ns(type="types-counts", type_column="ngram", count_column="pv_count"),
        )
        avail = introspect(conn, ds, level_order=self.LEVEL_ORDER)["availability"]
        assert avail["Canada"]["daily"] == {
            "min": "2024-01-01", "max": "2024-06-15", "types": 3}
        assert avail["Canada"]["weekly"] == {
            "min": "2024-01-07", "max": "2024-06-09", "types": 2}

    def test_other_endpoint_types_keep_bounds_only(self, conn, hive_types):
        ds = self._dataset(
            hive_types,
            _ns(type="time-series", type_column=None, count_column="pv_count"),
        )
        avail = introspect(conn, ds, level_order=self.LEVEL_ORDER)["availability"]
        assert avail["Canada"]["daily"] == {"min": "2024-01-01", "max": "2024-06-15"}

    def test_count_spans_hash_buckets_below_time_leaf(self, conn, tmp_path):
        """Types are disjoint across hash buckets — the count must sum them."""
        root = tmp_path / "bucketed"
        old = root / "country=Canada" / "date=2024-01-01" / "bucket=0"
        old.mkdir(parents=True)
        conn.execute(f"""
            COPY (SELECT 'cat' AS ngram, 10 AS pv_count)
            TO '{old / "data.parquet"}' (FORMAT PARQUET)
        """)
        new0 = root / "country=Canada" / "date=2024-06-15" / "bucket=0"
        new0.mkdir(parents=True)
        conn.execute(f"""
            COPY (
                SELECT * FROM (VALUES ('dog', 5), ('emu', 7)) AS t(ngram, pv_count)
            ) TO '{new0 / "data.parquet"}' (FORMAT PARQUET)
        """)
        new1 = root / "country=Canada" / "date=2024-06-15" / "bucket=1"
        new1.mkdir(parents=True)
        conn.execute(f"""
            COPY (SELECT 'fox' AS ngram, 3 AS pv_count)
            TO '{new1 / "data.parquet"}' (FORMAT PARQUET)
        """)
        ds = _ns(
            data_location=str(root),
            data_format="parquet_hive",
            transform=_ns(
                time_dimension="date",
                filter_dimensions=None,
                hash_bucket="bucket",
            ),
            entity_mapping=_ns(local_id_column="country"),
            endpoint_schema=_ns(
                type="types-counts", type_column="ngram", count_column="pv_count"),
        )
        level_order = [
            {"column": "country", "type": "entity", "default_value": "Canada"},
            {"column": "date", "type": "time", "default_value": "2024-01-01"},
            {"column": "bucket", "type": "hash_bucket", "default_value": 0},
        ]
        avail = introspect(conn, ds, level_order=level_order)["availability"]
        assert avail["Canada"] == {
            "min": "2024-01-01", "max": "2024-06-15", "types": 3}

    def test_flat_parquet_dataset_level_count(self, conn, flat_parquet):
        ds = _ns(
            data_location=flat_parquet,
            data_format="parquet",
            transform=_ns(
                time_dimension="year",
                filter_dimensions=None,
                hash_bucket=None,
            ),
            entity_mapping=None,
            endpoint_schema=_ns(
                type="types-counts", type_column="type", count_column="count"),
        )
        avail = introspect(conn, ds)["availability"]
        assert avail == {"min": "2015", "max": "2023", "types": 2}

    def test_flat_parquet_missing_type_column_degrades_to_bounds(self, conn, flat_parquet):
        """type_column=None defaults to 'types', absent here — bounds survive."""
        ds = _ns(
            data_location=flat_parquet,
            data_format="parquet",
            transform=_ns(
                time_dimension="year",
                filter_dimensions=None,
                hash_bucket=None,
            ),
            entity_mapping=None,
            endpoint_schema=_ns(
                type="types-counts", type_column=None, count_column=None),
        )
        avail = introspect(conn, ds)["availability"]
        assert avail == {"min": "2015", "max": "2023"}


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
