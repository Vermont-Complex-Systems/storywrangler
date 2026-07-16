"""Unit tests for the .df() accessor on API responses (no server needed)."""

import pytest

pd = pytest.importorskip("pandas")

from storywrangler.client import DataResponse, RecordList, _wrap


class TestDataResponse:
    def test_data_key(self):
        """top-ngrams shape: {'data': [...], 'metadata': {...}}"""
        r = DataResponse({
            "data": [{"types": "hello", "counts": 10}, {"types": "world", "counts": 5}],
            "metadata": {"location": "wikidata:Q30"},
        })
        df = r.df()
        assert list(df.columns) == ["types", "counts"]
        assert len(df) == 2

    def test_series_key(self):
        """term-series shape: {'type': ..., 'series': [...]}"""
        r = DataResponse({
            "type": "hello",
            "latest_available_date": "2026-05-01",
            "series": [{"date": "2026-05-01", "counts": 1, "rank": 2, "freq": 0.1}],
        })
        df = r.df()
        assert list(df.columns) == ["date", "counts", "rank", "freq"]

    def test_batch_series_dict(self):
        """term-series/batch shape: {'series': {term: [...]}}"""
        r = DataResponse({
            "series": {
                "hello": [{"date": "2026-05-01", "counts": 1}],
                "world": [{"date": "2026-05-01", "counts": 2}],
            },
        })
        df = r.df()
        assert set(df["type"]) == {"hello", "world"}
        assert len(df) == 2

    def test_dual_system_fallback(self):
        """dual-date top-ngrams shape: {'1991': [...], '2025': [...], 'metadata': ...}"""
        r = DataResponse({
            "1991": [{"types": "Ashley", "counts": 9}],
            "2025": [{"types": "Olivia", "counts": 7}],
            "metadata": {"sex": "F"},
        })
        df = r.df()
        assert set(df["system"]) == {"1991", "2025"}

    def test_single_list_fallback(self):
        """registry list shape: {'datasets': [...], 'total': 1}"""
        r = DataResponse({"datasets": [{"domain": "wikimedia", "dataset_id": "ngrams"}], "total": 1})
        assert r.df().iloc[0]["domain"] == "wikimedia"

    def test_no_tabular_payload_raises(self):
        with pytest.raises(ValueError, match="No tabular payload"):
            DataResponse({"detail": "not found"}).df()

    def test_still_a_dict(self):
        r = DataResponse({"data": [], "metadata": {"x": 1}})
        assert r["metadata"]["x"] == 1
        assert isinstance(r, dict)


class TestRecordList:
    def test_adapter_rows(self):
        rows = RecordList([{"local_id": "VT", "entity_id": "wikidata:Q16551"}])
        assert rows.df().iloc[0]["local_id"] == "VT"
        assert isinstance(rows, list)


class TestWrap:
    def test_wrap_types(self):
        assert isinstance(_wrap({"a": 1}), DataResponse)
        assert isinstance(_wrap([1, 2]), RecordList)
        assert _wrap("plain") == "plain"
