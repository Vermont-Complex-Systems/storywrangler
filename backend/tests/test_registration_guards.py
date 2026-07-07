"""
Tests for registration-time guards and the async DuckDB execution path.

Covers:
  - _validate_column_identifiers: declared column names must be plain SQL
    identifiers (they are interpolated unparameterized into DuckDB SQL)
  - run_blocking: results, exceptions, and contextvar propagation
    (Server-Timing segments recorded inside worker threads)
  - _fetch_top_articles: bucket-routed round-trip (write at the computed
    hash bucket, read back through the helper) and missing-file behaviour
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

# Ensure backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storywrangler_schemas.registry import DatasetCreate
from storywrangler_schemas.hashing import assign_bucket

from app.core.duckdb_client import run_blocking
from app.core.timing import get_timings, init_timings, timed
from app.routers.registry import _validate_column_identifiers
from app.routers.wikimedia import _fetch_top_articles


def make_dataset(**overrides) -> DatasetCreate:
    base = dict(
        catalog="vcsi",
        domain="wikimedia",
        dataset_id="test",
        data_location="/tmp/test.parquet",
        data_format="parquet",
        description="test dataset",
        ownership={"owner_group": "test-group", "contact": "test@example.org"},
        lineage={"repo": "https://github.com/example/test"},
    )
    base.update(overrides)
    return DatasetCreate(**base)


# ── _validate_column_identifiers ──────────────────────────────────────────────

class TestValidateColumnIdentifiers:
    def test_accepts_plain_identifiers(self):
        ds = make_dataset(
            endpoint_schema={"type": "types-counts", "type_column": "ngram", "count_column": "pv_count"},
            transform={"time_dimension": "date", "filter_dimensions": ["sex"]},
            entity_mapping={"local_id_column": "country"},
            data_schema={"ngram": "VARCHAR", "pv_count": "BIGINT", "_private": "INT"},
        )
        _validate_column_identifiers(ds)  # must not raise

    def test_rejects_sql_breakout_in_type_column(self):
        ds = make_dataset(
            endpoint_schema={"type": "types-counts", "type_column": "x; DROP TABLE users--"},
        )
        with pytest.raises(HTTPException) as exc:
            _validate_column_identifiers(ds)
        assert exc.value.status_code == 422

    def test_rejects_quote_in_provided_data_schema(self):
        ds = make_dataset(data_schema={"bad'col": "VARCHAR"})
        with pytest.raises(HTTPException) as exc:
            _validate_column_identifiers(ds)
        assert exc.value.status_code == 422
        # The offending field is named in the error (quote is repr-escaped)
        assert "data_schema" in str(exc.value.detail)

    def test_rejects_leading_digit_in_time_dimension(self):
        ds = make_dataset(transform={"time_dimension": "1date"})
        with pytest.raises(HTTPException) as exc:
            _validate_column_identifiers(ds)
        assert exc.value.status_code == 422

    def test_rejects_bad_filter_dimension(self):
        ds = make_dataset(
            transform={"time_dimension": "date", "filter_dimensions": ["ok_col", "not ok"]},
        )
        with pytest.raises(HTTPException) as exc:
            _validate_column_identifiers(ds)
        assert exc.value.status_code == 422

    def test_no_optional_fields_passes(self):
        _validate_column_identifiers(make_dataset())  # must not raise


# ── run_blocking ──────────────────────────────────────────────────────────────

class TestRunBlocking:
    def test_returns_result(self):
        assert asyncio.run(run_blocking(lambda: 42)) == 42

    def test_propagates_exception(self):
        def boom():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            asyncio.run(run_blocking(boom))

    def test_propagates_timing_contextvars(self):
        """timed() segments recorded inside the worker thread must be visible
        to the request's Server-Timing middleware."""
        async def main():
            init_timings()

            def work():
                with timed("seg", "in-thread work"):
                    pass

            await run_blocking(work)
            return get_timings()

        timings = asyncio.run(main())
        assert [t[0] for t in timings] == ["seg"]


# ── _fetch_top_articles ───────────────────────────────────────────────────────

def _articles_obj(root: str, default_count: int) -> SimpleNamespace:
    return SimpleNamespace(
        data_location=root,
        data_format="parquet_hive",
        transform={"hash_bucket": {"column": "ngram_bucket", "default_count": default_count}},
        level_order=[
            {"column": "ngram_size", "type": "partition", "default_value": 1},
            {"column": "country", "type": "entity", "default_value": "US"},
            {"column": "ngram_bucket", "type": "hash_bucket", "default_value": 0},
        ],
    )


class TestFetchTopArticles:
    def test_missing_files_returns_empty(self, conn):
        obj = _articles_obj("/nonexistent/top_articles", default_count=4)
        result = _fetch_top_articles(
            conn, obj, ["Trump"], "US", 1, "date <= ?", ["2024-01-01"],
        )
        assert result == {}

    def test_none_dataset_returns_empty(self, conn):
        assert _fetch_top_articles(conn, None, ["x"], "US", 1, "date <= ?", ["2024-01-01"]) == {}

    def test_bucket_round_trip(self, conn, tmp_path):
        """Write articles at the bucket assign_bucket() computes, then read
        them back through the helper — guards pipeline/query agreement."""
        default_count = 4
        term = "Trump"
        bucket = assign_bucket(term, default_count)

        leaf = tmp_path / "top_articles" / "ngram_size=1" / "country=US" / f"ngram_bucket={bucket}"
        leaf.mkdir(parents=True)
        conn.execute(f"""
            COPY (
                SELECT * FROM (VALUES
                    ('{term}', DATE '2024-01-01', 'https://en.wikipedia.org/wiki/Donald_Trump', 255.07, 1),
                    ('{term}', DATE '2024-01-01', 'https://en.wikipedia.org/wiki/Lara_Trump',   123.68, 2),
                    ('{term}', DATE '2024-01-02', 'https://en.wikipedia.org/wiki/Donald_Trump', 282.65, 1)
                ) AS t(ngram, date, article_url, score, article_rank)
            ) TO '{leaf / "data_0.parquet"}' (FORMAT PARQUET)
        """)

        obj = _articles_obj(str(tmp_path / "top_articles"), default_count)
        result = _fetch_top_articles(
            conn, obj, [term], "US", 1, "date <= ?", ["2024-01-02"],
        )

        assert set(result) == {(term, "2024-01-01"), (term, "2024-01-02")}
        # article_rank ordering preserved within a date
        assert result[(term, "2024-01-01")] == [
            ["https://en.wikipedia.org/wiki/Donald_Trump", 255.07],
            ["https://en.wikipedia.org/wiki/Lara_Trump", 123.68],
        ]
