"""
Tests for load_time_series() — the shared query utility for time-series endpoints.

Covers:
  - Basic GROUP BY aggregation
  - Single-value filters (col = ?)
  - Multi-value filters / IN clause (col IN (?, ?))
  - Time range filtering (BETWEEN)
  - No filters (aggregate everything)
  - Hive-partitioned parquet
  - Limit parameter
"""
import sys
from pathlib import Path

import pytest

# Ensure backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.query_utils import load_time_series
from tests.conftest import make_dataset_obj


class TestLoadTimeSeries:
    """Tests for load_time_series with flat parquet."""

    def test_group_by_field_year(self, conn, sample_parquet):
        """GROUP BY field, year — aggregates away venue and metric_type."""
        ds = make_dataset_obj(sample_parquet)
        result = load_time_series(
            conn, ds,
            group_cols=["field", "year"],
            filter_vals={"metric_type": "total"},
            limit=100,
        )
        # CS 2020: Nature(100) + Science(60) = 160
        cs_2020 = next(r for r in result if r["field"] == "Computer Science" and r["year"] == 2020)
        assert cs_2020["count"] == 160

        # Physics 2021: Nature(110) = 110
        ph_2021 = next(r for r in result if r["field"] == "Physics" and r["year"] == 2021)
        assert ph_2021["count"] == 110

    def test_single_value_filter(self, conn, sample_parquet):
        """Filter by field = 'Physics', metric_type = 'total'."""
        ds = make_dataset_obj(sample_parquet)
        result = load_time_series(
            conn, ds,
            group_cols=["year"],
            filter_vals={"field": "Physics", "metric_type": "total"},
            limit=100,
        )
        assert len(result) == 2  # 2020, 2021
        assert all(r["count"] > 0 for r in result)

    def test_multi_value_filter_in_clause(self, conn, sample_parquet):
        """Filter venue IN ('Nature', 'Science') — multi-value list."""
        ds = make_dataset_obj(sample_parquet)
        result = load_time_series(
            conn, ds,
            group_cols=["venue"],
            filter_vals={
                "venue": ["Nature", "Science"],
                "metric_type": "total",
                "field": "Computer Science",
            },
            limit=100,
        )
        venues = {r["venue"] for r in result}
        assert venues == {"Nature", "Science"}

    def test_multi_value_single_item_list(self, conn, sample_parquet):
        """A single-item list should work like equality."""
        ds = make_dataset_obj(sample_parquet)
        result = load_time_series(
            conn, ds,
            group_cols=["year"],
            filter_vals={"field": ["Physics"], "metric_type": "total"},
            limit=100,
        )
        assert len(result) == 2  # 2020, 2021

    def test_time_range(self, conn, sample_parquet):
        """Filter by time range: year >= 2021."""
        ds = make_dataset_obj(sample_parquet)
        result = load_time_series(
            conn, ds,
            group_cols=["field", "year"],
            filter_vals={"metric_type": "total"},
            start=2021,
            limit=100,
        )
        assert all(r["year"] >= 2021 for r in result)

    def test_time_range_between(self, conn, sample_parquet):
        """Filter by time range: 2020 <= year <= 2020."""
        ds = make_dataset_obj(sample_parquet)
        result = load_time_series(
            conn, ds,
            group_cols=["field"],
            filter_vals={"metric_type": "total"},
            start=2020,
            end=2020,
            limit=100,
        )
        # Only 2020 data: CS=160, Physics=90
        assert len(result) == 2

    def test_no_filters(self, conn, sample_parquet):
        """No filters — aggregates everything into one row per group."""
        ds = make_dataset_obj(sample_parquet)
        result = load_time_series(
            conn, ds,
            group_cols=["field"],
            filter_vals={},
            limit=100,
        )
        # Sums across all years, venues, and metric_types
        assert len(result) == 2  # CS, Physics

    def test_limit(self, conn, sample_parquet):
        """Limit constrains result count."""
        ds = make_dataset_obj(sample_parquet)
        result = load_time_series(
            conn, ds,
            group_cols=["field", "year", "venue"],
            filter_vals={"metric_type": "total"},
            limit=3,
        )
        assert len(result) <= 3

    def test_empty_result(self, conn, sample_parquet):
        """Non-existent filter value returns empty list."""
        ds = make_dataset_obj(sample_parquet)
        result = load_time_series(
            conn, ds,
            group_cols=["field"],
            filter_vals={"field": "Nonexistent"},
            limit=100,
        )
        assert result == []


class TestLoadTimeSeriesHive:
    """Tests for load_time_series with hive-partitioned parquet."""

    def test_hive_basic(self, conn, sample_hive_parquet):
        """Hive-partitioned parquet works with the same query logic."""
        ds = make_dataset_obj(sample_hive_parquet, data_format="parquet_hive")
        result = load_time_series(
            conn, ds,
            group_cols=["field", "year"],
            filter_vals={"metric_type": "total"},
            limit=100,
        )
        assert len(result) == 4  # CS×2020, CS×2021, Ph×2020, Ph×2021

    def test_hive_filter_partition_column(self, conn, sample_hive_parquet):
        """Filtering on hive partition column (field) prunes directories."""
        ds = make_dataset_obj(sample_hive_parquet, data_format="parquet_hive")
        result = load_time_series(
            conn, ds,
            group_cols=["year"],
            filter_vals={"field": "Physics", "metric_type": "total"},
            limit=100,
        )
        assert len(result) == 2
        assert all(r["count"] > 0 for r in result)

    def test_hive_multi_value_filter(self, conn, sample_hive_parquet):
        """IN clause works with hive-partitioned data."""
        ds = make_dataset_obj(sample_hive_parquet, data_format="parquet_hive")
        result = load_time_series(
            conn, ds,
            group_cols=["field"],
            filter_vals={
                "field": ["Computer Science", "Physics"],
                "metric_type": "total",
            },
            limit=100,
        )
        fields = {r["field"] for r in result}
        assert fields == {"Computer Science", "Physics"}
