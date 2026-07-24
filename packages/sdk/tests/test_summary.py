"""
Dataset summary surface — .summary rows, availability span, and the repr card.

The registration record is nested (availability trees, level_order) and does
not cast to a DataFrame; .summary is the flat, explorable view, and repr in
dataset mode shows the same facts as a card without a .meta round-trip.
"""
import pytest

from storywrangler.client import (
    DatasetClient, RecordList, _availability_span, _dataset_summary_rows,
)

HIVE_META = {
    "domain": "bluesky", "dataset_id": "ngrams", "version": "latest",
    "data_format": "parquet_hive", "dates": "range",
    "description": "Date-first ngram distributions for Bluesky.",
    "transform": {"time_dimension": "date", "filter_dimensions": ["lang", "n"]},
    "endpoint_schema": {"type": "types-counts", "type_column": "ngram",
                        "count_column": ["count", "count_all"]},
    "level_order": [
        {"column": "n", "type": "filter", "default_value": 1},
        {"column": "lang", "type": "filter", "default_value": "en"},
        {"column": "year", "type": "time_partition", "default_value": 2024},
    ],
    "filter_values": {"n": [1, 2], "lang": ["af", "de", "en"]},
    "manifest": {"availability": {
        "1": {"en": {"min": "2024-12-02", "max": "2026-01-04"},
              "de": {"min": "2024-12-05", "max": "2026-01-03"}}}},
}

FLAT_META = {
    "domain": "babynames", "dataset_id": "ngrams", "version": "latest",
    "data_format": "parquet", "dates": "range",
    "description": "US baby names.",
    "transform": {"time_dimension": "year", "filter_dimensions": ["sex"]},
    "endpoint_schema": {"type": "types-counts", "count_column": "counts"},
    "entity_mapping": {"local_id_column": "state"},
    "filter_values": {"sex": ["F", "M"]},
    "manifest": {"availability": {"min": "1880", "max": "2018"}},
}


def make_client(meta, domain="bluesky", dataset_id="ngrams"):
    client = DatasetClient(None, "http://unused", 1, domain, dataset_id)
    client._meta = meta
    client._meta_cache = {dataset_id: meta}
    return client


class TestAvailabilitySpan:
    def test_nested_tree(self):
        assert _availability_span(HIVE_META["manifest"]["availability"]) == (
            "2024-12-02", "2026-01-04")

    def test_flat_leaf_and_empty(self):
        assert _availability_span({"min": "1880", "max": "2018"}) == ("1880", "2018")
        assert _availability_span({}) == (None, None)
        assert _availability_span(None) == (None, None)

    def test_level_value_named_min_is_not_a_leaf(self):
        # bluesky has lang=min (Minangkabau): a key literally named "min"
        # whose value is a subtree — leaf detection must require scalar bounds.
        tree = {"1": {"min": {"min": "2024-12-02", "max": "2026-01-04"},
                      "en": {"min": "2024-11-01", "max": "2026-01-02"}}}
        assert _availability_span(tree) == ("2024-11-01", "2026-01-04")


class TestSummaryRows:
    def test_hive_rows(self):
        rows = {r["dimension"]: r for r in _dataset_summary_rows(HIVE_META)}
        # time_partition levels (year) are internal — not summary rows
        assert set(rows) == {"date", "n", "lang", "weight"}
        assert rows["date"]["kind"] == "time"
        assert rows["date"]["min"] == "2024-12-02" and rows["date"]["max"] == "2026-01-04"
        assert rows["lang"]["default"] == "en" and "af" in rows["lang"]["values"]
        assert rows["weight"]["default"] == "count"

    def test_flat_rows_with_entity(self):
        rows = {r["dimension"]: r for r in _dataset_summary_rows(FLAT_META)}
        assert rows["state"]["kind"] == "entity"
        assert rows["sex"]["kind"] == "filter" and rows["sex"]["default"] is None
        assert "weight" not in rows  # single measure → no menu row

    def test_summary_property_is_recordlist(self):
        s = make_client(HIVE_META).summary
        assert isinstance(s, RecordList) and len(s) == 4

    def test_summary_df(self):
        pd = pytest.importorskip("pandas")
        df = make_client(HIVE_META).summary.df()
        assert list(df.columns) == ["dimension", "kind", "default", "values", "min", "max"]
        assert len(df) == 4


class TestDatasetRepr:
    def test_card_shows_the_facts(self):
        text = repr(make_client(HIVE_META))
        assert "Dataset 'bluesky/ngrams'" in text and "parquet_hive" in text
        assert "default 'en'" in text
        assert "2024-12-02 → 2026-01-04" in text
        assert ".summary.df()" in text

    def test_offline_falls_back_to_identifier(self, monkeypatch):
        client = make_client(HIVE_META)
        monkeypatch.setattr(client, "_ensure_meta",
                            lambda: (_ for _ in ()).throw(RuntimeError("offline")))
        assert repr(client) == "DatasetClient('bluesky/ngrams')"
