"""
Tests for registration-time guards and the async DuckDB execution path.

Covers:
  - _validate_column_identifiers: declared column names must be plain SQL
    identifiers (they are interpolated unparameterized into DuckDB SQL)
  - run_blocking: results, exceptions, and contextvar propagation
    (Server-Timing segments recorded inside worker threads)
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

# Ensure backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storywrangler_schemas.registry import DatasetCreate

from app.core.duckdb_client import run_blocking
from app.core.timing import get_timings, init_timings, timed
from app.routers.registry import _validate_column_identifiers


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

    def test_rejects_injection_in_rank_and_freq_columns(self):
        # rank/freq reach the term-series SELECT list unparameterized.
        scalar = make_dataset(endpoint_schema={
            "type": "types-counts", "count_column": "c", "rank_column": "r; DROP TABLE t--"})
        with pytest.raises(HTTPException) as exc:
            _validate_column_identifiers(scalar)
        assert exc.value.status_code == 422
        parallel = make_dataset(endpoint_schema={
            "type": "types-counts", "count_column": ["a", "b"], "freq_column": ["fa", "f b"]})
        with pytest.raises(HTTPException):
            _validate_column_identifiers(parallel)

    def test_rejects_injection_in_doc_and_score_columns(self):
        for field in ("doc_column", "score_column"):
            ds = make_dataset(endpoint_schema={"type": "type-documents", field: "x'); DROP--"})
            with pytest.raises(HTTPException):
                _validate_column_identifiers(ds)

    def test_order_column_allows_direction_rejects_injection(self):
        _validate_column_identifiers(make_dataset(endpoint_schema={
            "type": "type-documents", "order_column": "article_rank DESC"}))  # must not raise
        with pytest.raises(HTTPException) as exc:
            _validate_column_identifiers(make_dataset(endpoint_schema={
                "type": "type-documents", "order_column": "score; DELETE FROM t"}))
        assert exc.value.status_code == 422

    def test_valid_companions_pass(self):
        _validate_column_identifiers(make_dataset(endpoint_schema={
            "type": "types-counts", "count_column": ["a", "b"],
            "rank_column": "rank", "freq_column": ["fa", "fb"]}))  # must not raise


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


# ── _apply_declared_defaults ──────────────────────────────────────────────────

class TestDeclaredDefaults:
    """transform.defaults overrides the auto-discovered (first-alphabetical)
    level_order defaults — validated so a typo fails at registration with a
    teaching 422, not silently at query time."""

    def _derived(self):
        return {
            "level_order": [
                {"column": "n", "type": "filter", "default_value": 1, "raw_value": "1"},
                {"column": "lang", "type": "filter", "default_value": "af", "raw_value": "af"},
                {"column": "year", "type": "time_partition", "default_value": 2006, "raw_value": "2006"},
                {"column": "ngram_bucket", "type": "hash_bucket", "default_value": 0, "raw_value": "0"},
            ],
            "filter_values": {"n": [1, 2], "lang": ["af", "de", "en"]},
            "data_schema": {"n": "BIGINT", "lang": "VARCHAR"},
        }

    def _apply(self, defaults, derived=None):
        from app.routers.registry import _apply_declared_defaults
        ds = make_dataset(transform={"time_dimension": "date",
                                     "filter_dimensions": ["lang", "n"],
                                     "defaults": defaults})
        derived = derived if derived is not None else self._derived()
        _apply_declared_defaults(ds, derived)
        return derived

    def test_override_applied_with_raw_value(self):
        derived = self._apply({"lang": "en", "n": 1})
        by_col = {lv["column"]: lv for lv in derived["level_order"]}
        assert by_col["lang"]["default_value"] == "en"
        assert by_col["lang"]["raw_value"] == "en"
        assert by_col["n"]["default_value"] == 1

    def test_string_value_coerced_via_schema(self):
        # Submitters may write "1"; data_schema says BIGINT → int 1.
        derived = self._apply({"n": "1"})
        by_col = {lv["column"]: lv for lv in derived["level_order"]}
        assert by_col["n"]["default_value"] == 1

    def test_unknown_column_teaches_422(self):
        with pytest.raises(HTTPException) as exc:
            self._apply({"language": "en"})
        assert exc.value.status_code == 422
        assert "queryable hive level" in exc.value.detail

    def test_non_queryable_level_teaches_422(self):
        # hash_bucket / time_partition levels are routing, not query axes.
        with pytest.raises(HTTPException) as exc:
            self._apply({"ngram_bucket": 3})
        assert exc.value.status_code == 422

    def test_value_not_on_disk_teaches_422(self):
        with pytest.raises(HTTPException) as exc:
            self._apply({"lang": "eng"})
        assert exc.value.status_code == 422
        assert "not among the on-disk values" in exc.value.detail

    def test_no_defaults_is_noop(self):
        derived = self._apply(None)
        assert {lv["column"]: lv["default_value"] for lv in derived["level_order"]}["lang"] == "af"

    def test_flat_dataset_has_no_levels_teaches_422(self):
        with pytest.raises(HTTPException) as exc:
            self._apply({"sex": "M"}, derived={"level_order": [], "filter_values": {}})
        assert exc.value.status_code == 422
