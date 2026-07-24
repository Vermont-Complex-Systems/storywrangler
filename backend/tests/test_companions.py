"""
Tests for lineage-based companion resolution (resolve_companions).

The term-series fast path (type-first sparkline) and ?include= provenance
(type-documents) are deduced from a primary dataset's declared companions —
datasets whose lineage.derived_from names it — classified by orientation/type.
This is what lets term-series drop the sparkline_dataset param and address
provenance by role instead of raw dataset id.
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.query_utils import resolve_companions


class _FakeResult:
    def __init__(self, entries):
        self._entries = entries

    def scalars(self):
        return self

    def all(self):
        return self._entries


class _FakeDB:
    """Async session stub — returns preset entries in the query's sort order."""

    def __init__(self, entries):
        self._entries = entries

    async def execute(self, *_a, **_k):
        return _FakeResult(self._entries)


def _entry(dataset_id, *, etype=None, orientation=None, role=None, derived=None,
           version="latest"):
    ep = {}
    if etype:
        ep["type"] = etype
    if orientation:
        ep["orientation"] = orientation
    if role:
        ep["role"] = role
    return SimpleNamespace(
        dataset_id=dataset_id, version=version,
        endpoint_schema=ep or None,
        lineage={"derived_from": derived} if derived else None,
    )


def _resolve(entries, domain="wikimedia", dataset="ngrams"):
    return asyncio.run(resolve_companions(_FakeDB(entries), domain, dataset))


class TestResolveCompanions:
    def test_full_corpus(self):
        # The canonical shape: a time-first primary, a type-first sparkline, and
        # a type-documents provenance set — the last two derived from the primary.
        entries = [
            _entry("ngrams", etype="types-counts"),  # primary (time-first default)
            _entry("sparklines", etype="types-counts", orientation="type-first",
                   derived=["wikimedia/ngrams"]),
            _entry("top_articles_ngrams", etype="type-documents", role="articles",
                   derived=["wikimedia/ngrams"]),
        ]
        got = _resolve(entries)
        assert got["type_first"].dataset_id == "sparklines"
        assert set(got["documents"]) == {"articles"}
        assert got["documents"]["articles"].dataset_id == "top_articles_ngrams"

    def test_type_documents_without_role_keyed_by_id(self):
        entries = [
            _entry("ngrams", etype="types-counts"),
            _entry("top_articles_ngrams", etype="type-documents",
                   derived=["wikimedia/ngrams"]),
        ]
        got = _resolve(entries)
        assert set(got["documents"]) == {"top_articles_ngrams"}

    def test_unrelated_derived_from_ignored(self):
        # A type-first dataset derived from a *different* primary is not a
        # companion — pairing is by declared provenance, not structure.
        entries = [
            _entry("ngrams", etype="types-counts"),
            _entry("other_sparklines", etype="types-counts", orientation="type-first",
                   derived=["wikimedia/other"]),
        ]
        got = _resolve(entries)
        assert got["type_first"] is None
        assert got["documents"] == {}

    def test_time_first_companion_is_not_the_fast_path(self):
        # Only orientation=type-first counts as the sparkline; a derived
        # time-first types-counts is not the fast path.
        entries = [
            _entry("ngrams", etype="types-counts"),
            _entry("ngrams_rollup", etype="types-counts", orientation="time-first",
                   derived=["wikimedia/ngrams"]),
        ]
        assert _resolve(entries)["type_first"] is None

    def test_no_companions(self):
        got = _resolve([_entry("ngrams", etype="types-counts")])
        assert got == {"type_first": None, "documents": {}}


class TestSelfTypeFirst:
    """A dataset that is itself type-first serves as its own fast path."""

    def _resolve_sparkline(self, dataset_obj, companions):
        from app.core.term_series import _resolve_type_first
        return asyncio.run(
            _resolve_type_first(None, "bluesky", dataset_obj, companions, None))

    def test_type_first_primary_resolves_itself(self):
        # bluesky/ngrams: the queried dataset IS the term-bucketed tree — no
        # companion exists (a dataset cannot derive from itself), so the
        # orientation on its own registration makes it the fast path.
        primary = _entry("ngrams", etype="types-counts", orientation="type-first")
        got = self._resolve_sparkline(primary, {"type_first": None, "documents": {}})
        assert got is primary

    def test_time_first_primary_uses_companion(self):
        primary = _entry("ngrams", etype="types-counts")
        sparkline = _entry("sparklines", etype="types-counts", orientation="type-first",
                           derived=["wikimedia/ngrams"])
        got = self._resolve_sparkline(primary, {"type_first": sparkline, "documents": {}})
        assert got is sparkline

    def test_undeclared_orientation_no_companion_no_fast_path(self):
        primary = _entry("ngrams", etype="types-counts")
        got = self._resolve_sparkline(primary, {"type_first": None, "documents": {}})
        assert got is None


class TestFetchIncludesCoverage:
    def test_non_covering_companion_skipped(self):
        # A provenance companion with no granularity level would attach
        # documents from the wrong slice — it is skipped, not queried.
        from app.core.term_series import fetch_includes
        prov = SimpleNamespace(
            dataset_id="ngrams-articles",
            endpoint_schema={"type": "type-documents", "role": "articles"},
            level_order=[{"column": "ngram_size", "type": "partition"},
                         {"column": "country", "type": "entity"},
                         {"column": "ngram_bucket", "type": "hash_bucket"}],
        )
        from app.core.term_series import SeriesCtx
        ctx = SeriesCtx(
            dataset_obj=None,
            companions={"documents": {"articles": prov}},
            filter_vals={"ngram_size": 1, "granularity": "weekly"},
            local_id="United States", time_col="date",
        )
        out = asyncio.run(fetch_includes(None, "wikimedia", "articles", ctx, {"trump"}))
        assert out == {}


class TestIncludeDates:
    def test_include_dates_narrows_provenance_read(self, monkeypatch):
        # include_dates scopes the provenance query to exact dates (IN list)
        # while the series keeps its own range.
        import app.core.term_series as ts

        prov = SimpleNamespace(
            dataset_id="ngrams-articles",
            endpoint_schema={"type": "type-documents", "role": "articles"},
            level_order=[{"column": "ngram_size", "type": "partition"},
                         {"column": "country", "type": "entity"},
                         {"column": "bucket", "type": "hash_bucket"}],
        )
        from app.core.term_series import SeriesCtx
        ctx = SeriesCtx(
            dataset_obj=None,
            companions={"documents": {"articles": prov}},
            filter_vals={"ngram_size": 1},
            local_id="United States",
            date_filter="date BETWEEN ? AND ?",
            date_params=["2026-01-01", "2026-01-31"],
            time_col="date",
        )

        seen = {}

        def fake_fetch_provenance(conn, obj, terms, *, date_condition, date_params, **kw):
            seen["condition"], seen["params"] = date_condition, date_params
            return {}

        class _Client:
            def timed_connect(self):
                from contextlib import contextmanager
                @contextmanager
                def cm():
                    yield None
                return cm()

        async def fake_run_blocking(fn):
            return fn()

        monkeypatch.setattr(ts, "fetch_provenance", fake_fetch_provenance)
        monkeypatch.setattr(ts, "get_duckdb_client", lambda: _Client())
        monkeypatch.setattr(ts, "run_blocking", fake_run_blocking)

        asyncio.run(ts.fetch_includes(
            None, "wikimedia", "articles", ctx, {"trump"},
            include_dates="2026-01-20,2026-01-21"))
        assert seen["condition"] == "date IN (?, ?)"
        assert seen["params"] == ["2026-01-20", "2026-01-21"]

        # Omitted → the series' own bounds apply.
        asyncio.run(ts.fetch_includes(None, "wikimedia", "articles", ctx, {"trump"}))
        assert seen["condition"] == "date BETWEEN ? AND ?"
        assert seen["params"] == ["2026-01-01", "2026-01-31"]
