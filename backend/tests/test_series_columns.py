"""
Tests for resolve_series_columns() — the declared rank/freq companion resolver.

Covers the scalar-vs-parallel-list contract (reddit canonical rank, bluesky
per-measure rank, wiki fixed) and the undeclared → None fallback signal.
"""
import sys
from pathlib import Path

# Ensure backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.query_utils import resolve_series_columns
from tests.conftest import make_dataset_obj


def ds(endpoint_schema):
    return make_dataset_obj("/data", endpoint_schema=endpoint_schema)


class TestResolveSeriesColumns:
    def test_undeclared_returns_none(self):
        # No rank/freq declared → signal to fall back to legacy derivation.
        d = ds({"type": "types-counts", "type_column": "ngram", "count_column": "count"})
        assert resolve_series_columns(d) is None

    def test_wiki_style_scalars(self):
        d = ds({"type": "types-counts", "type_column": "ngram",
                "count_column": "pv_count", "rank_column": "pv_rank", "freq_column": "pv_freq"})
        assert resolve_series_columns(d) == {
            "count": "pv_count", "rank": "pv_rank", "freq": "pv_freq"}

    def test_reddit_scalar_rank_parallel_freq(self):
        # Canonical rank (scalar, weight-independent) + per-measure freq (list).
        d = ds({
            "type": "types-counts", "type_column": "ngram",
            "count_column": ["all_score_weighted", "comments_unweighted"],
            "rank_column": "rank",
            "freq_column": ["all_score_freq", "comments_unweighted_freq"],
        })
        # default weight (index 0)
        assert resolve_series_columns(d) == {
            "count": "all_score_weighted", "rank": "rank", "freq": "all_score_freq"}
        # chosen weight (index 1) — rank stays canonical, freq tracks the measure
        assert resolve_series_columns(d, "comments_unweighted") == {
            "count": "comments_unweighted", "rank": "rank", "freq": "comments_unweighted_freq"}

    def test_bluesky_per_measure_rank_and_freq(self):
        d = ds({
            "type": "types-counts", "type_column": "ngram",
            "count_column": ["count", "count_all"],
            "rank_column": ["rank", "rank_all"],
            "freq_column": ["freq", "freq_all"],
        })
        assert resolve_series_columns(d, "count") == {
            "count": "count", "rank": "rank", "freq": "freq"}
        assert resolve_series_columns(d, "count_all") == {
            "count": "count_all", "rank": "rank_all", "freq": "freq_all"}

    def test_freq_only(self):
        # rank absent, freq declared → rank None, freq resolved (not a fallback).
        d = ds({"type": "types-counts", "type_column": "ngram",
                "count_column": "count", "freq_column": "freq"})
        assert resolve_series_columns(d) == {"count": "count", "rank": None, "freq": "freq"}


class TestCompanionValidation:
    """The EndpointSchemaConfig validator: list companions must parallel count_column."""

    def _validate(self, ep):
        from storywrangler_schemas.registry import EndpointSchemaConfig
        return EndpointSchemaConfig.model_validate(ep)

    def test_scalar_always_ok(self):
        self._validate({"type": "types-counts", "count_column": ["a", "b"], "rank_column": "rank"})

    def test_parallel_list_ok(self):
        self._validate({"type": "types-counts", "count_column": ["a", "b"],
                        "rank_column": ["ra", "rb"], "freq_column": ["fa", "fb"]})

    def test_list_companion_without_list_count_rejected(self):
        import pytest
        with pytest.raises(ValueError, match="requires count_column to be a parallel list"):
            self._validate({"type": "types-counts", "count_column": "a", "rank_column": ["ra", "rb"]})

    def test_length_mismatch_rejected(self):
        import pytest
        with pytest.raises(ValueError, match="parallel to count_column"):
            self._validate({"type": "types-counts", "count_column": ["a", "b", "c"],
                            "freq_column": ["fa", "fb"]})


class TestTypeDocuments:
    """The type-documents provenance endpoint schema (?include=)."""

    def test_accepts_doc_score_order(self):
        from storywrangler_schemas.registry import EndpointSchemaConfig
        ep = EndpointSchemaConfig.model_validate({
            "type": "type-documents", "type_column": "ngram",
            "doc_column": "article_url", "score_column": "score",
            "order_column": "article_rank",
        })
        assert ep.doc_column == "article_url"
        assert ep.score_column == "score"
        assert ep.order_column == "article_rank"

    def test_type_is_supported(self):
        from storywrangler_schemas.registry import _SUPPORTED_ENDPOINT_TYPES
        assert "type-documents" in _SUPPORTED_ENDPOINT_TYPES


class TestOrientationAndRole:
    """orientation scopes to types-counts; role scopes to type-documents."""

    def _validate(self, ep):
        from storywrangler_schemas.registry import EndpointSchemaConfig
        return EndpointSchemaConfig.model_validate(ep)

    def test_orientation_on_types_counts(self):
        for o in ("time-first", "type-first"):
            assert self._validate(
                {"type": "types-counts", "count_column": "c", "orientation": o}
            ).orientation == o

    def test_orientation_defaults_none(self):
        # Omitted → None, which the resolver reads as time-first (back-compat).
        assert self._validate({"type": "types-counts", "count_column": "c"}).orientation is None

    def test_orientation_rejected_on_type_documents(self):
        import pytest
        with pytest.raises(ValueError, match="orientation applies only to types-counts"):
            self._validate({"type": "type-documents", "doc_column": "d",
                            "score_column": "s", "orientation": "type-first"})

    def test_role_on_type_documents(self):
        ep = self._validate({"type": "type-documents", "doc_column": "d",
                             "score_column": "s", "role": "articles"})
        assert ep.role == "articles"

    def test_role_rejected_on_types_counts(self):
        import pytest
        with pytest.raises(ValueError, match="role applies only to type-documents"):
            self._validate({"type": "types-counts", "count_column": "c", "role": "articles"})

    def test_invalid_orientation_value(self):
        import pytest
        with pytest.raises(ValueError):
            self._validate({"type": "types-counts", "count_column": "c",
                            "orientation": "sideways"})
