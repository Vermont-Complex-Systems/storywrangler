"""
Tests for the format-agnostic generic term-series query construction.

Covers the scan-target dispatch (parquet_hive path-pinning vs flat-parquet
in-file WHERE) and the mongodb date-range sub-filter — the pieces that let
/storywrangler/term-series serve hive, flat, and mongo like top-ngrams does.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.mongo_query import date_range_filter
from app.core.term_series import _term_series_scan_target


def _ctx(dataset_obj, **kw):
    base = dict(dataset_obj=dataset_obj, local_id=None, filter_vals={},
                date_params=[], base_path=None, type_col="ngram", time_col="date")
    base.update(kw)
    return SimpleNamespace(**base)


class TestScanTargetHive:
    HIVE = SimpleNamespace(
        level_order=[
            {"column": "n", "type": "filter"},
            {"column": "lang", "type": "filter"},
            {"column": "year", "type": "time_partition"},
            {"column": "month", "type": "time_partition"},
        ],
        data_location="/data/reddit", entity_mapping=None, dataset_id="ngrams",
    )

    def test_narrow_range_pins_year(self):
        ctx = _ctx(self.HIVE, filter_vals={"n": 1, "lang": "en"},
                   date_params=["2022-06-01", "2022-06-20"], type_col="ngram", time_col="date")
        frm, where, params = _term_series_scan_target(ctx)
        assert "year=2022" in frm and "hive_partitioning=true" in frm
        assert where == ["month IN (?,?)"] and params == [5, 6]

    def test_wide_range_wildcards(self):
        ctx = _ctx(self.HIVE, filter_vals={"n": 1, "lang": "en"},
                   date_params=["2021-06-01", "2022-05-31"])
        frm, where, params = _term_series_scan_target(ctx)
        # year spans two → WHERE IN, path wildcards year/month
        assert "year IN (?,?)" in where and 2021 in params and 2022 in params


class TestScanTargetFlat:
    FLAT = SimpleNamespace(
        level_order=None, data_location="/data/babynames/names.parquet",
        entity_mapping={"local_id_column": "country"}, dataset_id="ngrams",
    )

    def test_flat_reads_location_with_where(self):
        ctx = _ctx(self.FLAT, local_id="United States", filter_vals={"sex": "M"},
                   date_params=["1990", "2000"], type_col="name", time_col="year")
        frm, where, params = _term_series_scan_target(ctx)
        assert frm == "read_parquet('/data/babynames/names.parquet')"
        assert "country = ?" in where and "sex = ?" in where
        assert params == ["United States", "M"]

    def test_flat_no_entity_no_filters(self):
        obj = SimpleNamespace(level_order=None, data_location="/d/x.parquet",
                              entity_mapping=None, dataset_id="ngrams")
        frm, where, params = _term_series_scan_target(_ctx(obj))
        assert frm == "read_parquet('/d/x.parquet')" and where == [] and params == []


class TestMongoDateRangeFilter:
    STR_TIME = SimpleNamespace(data_schema={"time": "VARCHAR"})
    DT_TIME = SimpleNamespace(data_schema={"time": "TIMESTAMP"})

    def test_string_time_range(self):
        assert date_range_filter(self.STR_TIME, "time", ["2022-01-01", "2022-03-01"]) == {
            "$gte": "2022-01-01", "$lte": "2022-03-01"}

    def test_datetime_time_pads_end(self):
        f = date_range_filter(self.DT_TIME, "time", ["2022-01-01", "2022-03-01"])
        assert f["$gte"].isoformat() == "2022-01-01T00:00:00"
        assert f["$lt"].isoformat() == "2022-03-02T00:00:00"  # end + 1 day

    def test_none_is_full_history(self):
        assert date_range_filter(self.STR_TIME, "time", None) is None


class TestBucketReadStrict:
    """The self-served bucket read: missing shards are an honest empty, but
    real query errors re-raise (there is no fallback behind this read)."""

    def _bucketed_obj(self, root, default_count=4):
        return SimpleNamespace(
            data_location=str(root), data_format="parquet_hive",
            transform={"hash_bucket": {"column": "ngram_bucket",
                                       "default_count": default_count}},
            level_order=[
                {"column": "n", "type": "partition", "default_value": 1},
                {"column": "ngram_bucket", "type": "hash_bucket", "default_value": 0},
            ],
        )

    def _read(self, conn, obj, select_cols, strict):
        from app.core.term_series import fetch_sparkline_rows
        return fetch_sparkline_rows(
            conn, obj, ["trump"], entity_value=None, filter_vals={"n": 1},
            select_cols=select_cols, date_condition="1=1", date_params=[],
            label="t", strict=strict)

    def _write_bucket(self, conn, tmp_path):
        from storywrangler_schemas.hashing import assign_bucket
        bucket = assign_bucket("trump", 4)
        leaf = tmp_path / "tree" / "n=1" / f"ngram_bucket={bucket}"
        leaf.mkdir(parents=True)
        conn.execute(f"""
            COPY (SELECT 'trump' AS ngram, DATE '2024-01-01' AS date, 5 AS count)
            TO '{leaf / "data.parquet"}' (FORMAT PARQUET)
        """)
        return tmp_path / "tree"

    def test_missing_shard_is_empty_even_strict(self, conn):
        obj = self._bucketed_obj("/nonexistent/tree")
        assert self._read(conn, obj, "ngram, date, count", strict=True) == []

    def test_round_trip(self, conn, tmp_path):
        obj = self._bucketed_obj(self._write_bucket(conn, tmp_path))
        rows = self._read(conn, obj, "ngram, date, count", strict=True)
        assert [(r[0], str(r[1]), r[2]) for r in rows] == [("trump", "2024-01-01", 5)]

    def test_real_error_swallowed_when_lax(self, conn, tmp_path):
        # A bad column is a Binder error, not data-missing: the companion fast
        # path logs and returns [] (the scan fallback covers it).
        obj = self._bucketed_obj(self._write_bucket(conn, tmp_path))
        assert self._read(conn, obj, "ngram, date, missing_col", strict=False) == []

    def test_real_error_raises_when_strict(self, conn, tmp_path):
        import pytest
        obj = self._bucketed_obj(self._write_bucket(conn, tmp_path))
        with pytest.raises(Exception, match="missing_col"):
            self._read(conn, obj, "ngram, date, missing_col", strict=True)


class TestCompanionCovers:
    """The coverage gate: a companion must have a hive level for every request
    filter dim, else its files would answer for the wrong slice."""

    def _companion(self, *cols):
        from app.core.term_series import _companion_covers  # noqa: F401
        return SimpleNamespace(
            level_order=[{"column": c, "type": "partition"} for c in cols])

    def test_covers_when_all_dims_are_levels(self):
        from app.core.term_series import _companion_covers
        assert _companion_covers(
            self._companion("ngram_size", "granularity", "country", "ngram_bucket"),
            {"ngram_size": 1, "granularity": "weekly"})

    def test_missing_dim_not_covered(self):
        # The daily-sparkline trap: no granularity level → cannot answer
        # granularity=weekly (or daily — the path can't pin the slice at all).
        from app.core.term_series import _companion_covers
        assert not _companion_covers(
            self._companion("ngram_size", "country", "ngram_bucket"),
            {"ngram_size": 1, "granularity": "weekly"})

    def test_no_filters_trivially_covered(self):
        from app.core.term_series import _companion_covers
        assert _companion_covers(self._companion(), {})
        assert _companion_covers(SimpleNamespace(level_order=None), {})
