"""
Client-side pre-flight validation — the dates contract.

DatasetClient.top_ngrams validates dates against the registry's derived
`dates` field ('none' | 'single' | 'range') before any request goes out:
dateless datasets reject dates entirely, mongodb pass-through datasets reject
ranges. Metadata is stubbed; the failure paths never touch the network.
"""
import pytest

from storywrangler.client import DatasetClient


def make_client(meta: dict, domain: str = "d", dataset_id: str = "ds") -> DatasetClient:
    client = DatasetClient(None, "http://unused", 1, domain, dataset_id)
    client._meta = meta
    client._meta_cache = {dataset_id: meta}
    return client


class TestValidateDates:
    def test_dateless_dataset_rejects_dates(self):
        client = make_client({"dates": "none"})
        with pytest.raises(ValueError, match="no time dimension"):
            client.top_ngrams(dates="2020-01-01")

    def test_mongodb_rejects_range(self):
        client = make_client({"dates": "single"})
        with pytest.raises(ValueError, match="single YYYY-MM-DD"):
            client.top_ngrams(dates="2020-01-01,2020-01-31")

    def test_omitting_dates_skips_validation(self):
        # No dates → nothing to validate, even for a dateless dataset.
        client = make_client({"dates": "none"})
        client._validate_dates(None, None)  # no raise

    def test_range_ok_for_parquet(self):
        client = make_client({"dates": "range"})
        client._validate_dates("2020-01-01,2020-01-31", None)  # no raise

    def test_missing_dates_field_skips_validation(self):
        # An older backend that doesn't surface the derived 'dates' field:
        # pre-flight is skipped (graceful), the server's 400 teaches instead.
        client = make_client({"transform": {"time_dimension": "time"},
                              "data_format": "mongodb"})
        client._validate_dates("2020-01-01,2020-01-31", None)  # no raise
