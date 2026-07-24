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
from app.core.term_series import SeriesCtx, _scan_target


def _ctx(dataset_obj, **kw):
    base = dict(local_id=None, filter_vals={}, date_params=[],
                type_col="ngram", time_col="date")
    base.update(kw)
    return SeriesCtx(dataset_obj=dataset_obj, **base)


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
        frm, where, params = _scan_target(ctx)
        assert "year=2022" in frm and "hive_partitioning=true" in frm
        assert where == ["month IN (?,?)"] and params == [5, 6]

    def test_wide_range_wildcards(self):
        ctx = _ctx(self.HIVE, filter_vals={"n": 1, "lang": "en"},
                   date_params=["2021-06-01", "2022-05-31"])
        frm, where, params = _scan_target(ctx)
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
        frm, where, params = _scan_target(ctx)
        assert frm == "read_parquet('/data/babynames/names.parquet')"
        assert "country = ?" in where and "sex = ?" in where
        assert params == ["United States", "M"]

    def test_flat_no_entity_no_filters(self):
        obj = SimpleNamespace(level_order=None, data_location="/d/x.parquet",
                              entity_mapping=None, dataset_id="ngrams")
        frm, where, params = _scan_target(_ctx(obj))
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
        from app.core.type_first import fetch_sparkline_rows
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


class TestPerMissingTermFallback:
    """A batch mixing vocabulary and out-of-vocabulary terms scans ONLY the
    missing terms — a sparkline hit for one term must not suppress the scan
    for its siblings (they'd read as silently empty series)."""

    FLAT = SimpleNamespace(level_order=None, data_location="/d/x.parquet",
                           entity_mapping=None, dataset_id="ngrams")

    def _ctx(self, *, dated=True, type_first=True):
        # dated by default: the undated+missing+sparkline combination is the
        # teaching-400 case, tested separately below.
        date_filter, date_params = (
            ("date BETWEEN ? AND ?", ["2024-01-01", "2024-01-31"]) if dated
            else ("1=1", []))
        return SeriesCtx(
            dataset_obj=self.FLAT,
            type_first_obj=SimpleNamespace(dataset_id="sparklines") if type_first else None,
            select_cols="ngram, date, c, NULL, NULL",
            latest_date="2024-01-31",
            date_filter=date_filter, date_params=date_params,
            type_col="ngram", time_col="date",
        )

    def _run(self, monkeypatch, ctx, fast_rows, scan_rows):
        import asyncio
        import app.core.term_series as ts

        seen = {"scan_params": None}

        class _Conn:
            def execute(self, sql, params):
                seen["scan_params"] = params
                return SimpleNamespace(fetchall=lambda: scan_rows)

        class _Client:
            def timed_connect(self):
                from contextlib import contextmanager
                @contextmanager
                def cm():
                    yield _Conn()
                return cm()

        async def fake_run_blocking(fn):
            return fn()

        monkeypatch.setattr(ts, "fetch_sparkline_rows",
                            lambda conn, obj, terms, **kw: fast_rows)
        monkeypatch.setattr(ts, "get_duckdb_client", lambda: _Client())
        monkeypatch.setattr(ts, "run_blocking", fake_run_blocking)

        rows = asyncio.run(ts.term_series_rows("wikimedia", ctx, ["the", "Zykov"]))
        return rows, seen["scan_params"]

    def test_missing_term_scanned_found_term_kept(self, monkeypatch):
        fast = [("the", "2024-01-01", 5, None, None)]
        scanned = [("Zykov", "2024-01-01", 1, None, None)]
        rows, scan_params = self._run(monkeypatch, self._ctx(), fast, scanned)
        assert rows == [*fast, *scanned]
        # only the missing term reaches the scan (+ the date bounds)
        assert scan_params == ["Zykov", "2024-01-01", "2024-01-31"]

    def test_all_found_skips_scan(self, monkeypatch):
        fast = [("the", "2024-01-01", 5, None, None),
                ("Zykov", "2024-01-01", 1, None, None)]
        rows, scan_params = self._run(monkeypatch, self._ctx(dated=False), fast, [])
        assert rows == fast
        assert scan_params is None  # scan never ran (undated is fine: no miss)

    def test_none_found_scans_all(self, monkeypatch):
        scanned = [("the", "2024-01-01", 5, None, None)]
        rows, scan_params = self._run(monkeypatch, self._ctx(), [], scanned)
        assert rows == scanned
        assert scan_params == ["the", "Zykov", "2024-01-01", "2024-01-31"]

    def test_undated_miss_on_sparkline_dataset_teaches_400(self, monkeypatch):
        # Undated full history is a fast-path privilege: a vocabulary miss
        # without dates= must not launch an unbounded scan of the raw tree.
        import pytest
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            self._run(monkeypatch, self._ctx(dated=False), [], [])
        assert exc.value.status_code == 400
        assert "Zykov" in exc.value.detail and "dates=" in exc.value.detail

    def test_undated_scan_allowed_without_fast_path(self, monkeypatch):
        # A dataset with no type-first form lives by the scan — undated
        # full-history reads are its normal usage (babynames, scisciDB).
        scanned = [("the", "2024-01-01", 5, None, None)]
        rows, scan_params = self._run(
            monkeypatch, self._ctx(dated=False, type_first=False), [], scanned)
        assert rows == scanned
        assert scan_params == ["the", "Zykov"]
