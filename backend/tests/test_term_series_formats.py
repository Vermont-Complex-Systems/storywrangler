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
from app.routers.storywrangler import _term_series_scan_target


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
