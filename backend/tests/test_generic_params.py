"""
Tests for the generic-endpoint parameter helpers (/storywrangler/*).

Covers:
  - extract_filter_vals(): ?dim=val extraction, ?dim2=val (suffix), default
    injection from level_order, validation/coercion against filter_values
  - require_types_counts(): endpoint_schema gate
  - require_single_dates(): mongodb single-date guard
"""
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

# Ensure backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.mongo_query import require_single_dates
from app.core.query_utils import (
    dates_mode, extract_filter_pair, extract_filter_vals, latest_available_for,
    require_dates_supported, require_types_counts,
)
from tests.conftest import make_dataset_obj


def _with_availability(availability):
    ds = make_dataset_obj("/data")
    ds.manifest = {"availability": availability}
    return ds


class TestLatestAvailableFor:
    def test_reddit_style_nlang(self):
        # {n: {lang: {min, max}}} — navigate by filter values.
        ds = _with_availability({"1": {"en": {"min": "2010-01-01", "max": "2022-12-31"},
                                       "es": {"min": "2011-01-01", "max": "2023-06-30"}}})
        assert latest_available_for(ds, None, {"n": 1, "lang": "es"}) == "2023-06-30"
        assert latest_available_for(ds, None, {"n": 1, "lang": "en"}) == "2022-12-31"

    def test_wikimedia_style_entity_first(self):
        # {country: {ngram_size: {granularity: {min, max}}}} — entity + filters.
        ds = _with_availability({
            "United States": {"1": {"daily": {"min": "2015-01-01", "max": "2026-04-20"}}}})
        assert latest_available_for(
            ds, "United States", {"ngram_size": 1, "granularity": "daily"}) == "2026-04-20"

    def test_no_match_falls_back_to_first_branch(self):
        ds = _with_availability({"1": {"en": {"min": "2010-01-01", "max": "2022-12-31"}}})
        # lang not present → first branch
        assert latest_available_for(ds, None, {"n": 1, "lang": "zz"}) == "2022-12-31"

    def test_empty_availability(self):
        ds = _with_availability({})
        assert latest_available_for(ds, None, {}) is None


LEVEL_ORDER = [
    {"column": "ngram_size", "type": "partition", "default_value": 1},
    {"column": "granularity", "type": "partition", "default_value": "daily"},
    {"column": "country", "type": "entity", "default_value": "Afghanistan"},
    {"column": "date", "type": "time", "default_value": "2020-01-01"},
]

FILTER_VALUES = {
    "ngram_size": [1, 2],
    "granularity": ["daily", "weekly", "monthly"],
}


def hive_dataset():
    return make_dataset_obj(
        "/data/ngrams",
        data_format="parquet_hive",
        level_order=LEVEL_ORDER,
        filter_values=FILTER_VALUES,
    )


class TestExtractFilterVals:
    def test_defaults_injected_when_params_absent(self):
        vals = extract_filter_vals(hive_dataset(), {})
        assert vals == {"ngram_size": 1, "granularity": "daily"}

    def test_param_overrides_default(self):
        vals = extract_filter_vals(hive_dataset(), {"granularity": "weekly"})
        assert vals == {"ngram_size": 1, "granularity": "weekly"}

    def test_unknown_params_ignored(self):
        # Endpoint-level params (dates, entity, ...) are not filter dims.
        vals = extract_filter_vals(
            hive_dataset(), {"dates": "2024-01-01", "entity": "wikidata:Q30"})
        assert vals == {"ngram_size": 1, "granularity": "daily"}

    def test_suffix_reads_system2_params(self):
        params = {"granularity": "weekly", "granularity2": "monthly"}
        assert extract_filter_vals(hive_dataset(), params)["granularity"] == "weekly"
        assert extract_filter_vals(hive_dataset(), params, suffix="2")["granularity"] == "monthly"

    def test_string_value_coerced_to_typed(self):
        # Query params arrive as strings; filter_values stores ints.
        vals = extract_filter_vals(hive_dataset(), {"ngram_size": "2"})
        assert vals["ngram_size"] == 2

    def test_invalid_value_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            extract_filter_vals(hive_dataset(), {"granularity": "hourly"})
        assert exc.value.status_code == 400
        assert "granularity" in exc.value.detail

    def test_no_level_order_falls_back_to_filter_dimensions(self):
        # Flat parquet: dims come from transform.filter_dimensions, no defaults.
        ds = make_dataset_obj(
            "/data/flat.parquet",
            transform={"time_dimension": "year", "filter_dimensions": ["sex"]},
            filter_values={"sex": ["F", "M"]},
        )
        assert extract_filter_vals(ds, {}) == {}
        assert extract_filter_vals(ds, {"sex": "M"}) == {"sex": "M"}


class TestExtractFilterPair:
    """System 2 inherits system 1's filters per dimension unless overridden with
    ?dim2= — the single convention behind allotax / rtd / wordshift."""

    def _flat(self):
        return make_dataset_obj(
            "/data/flat.parquet",
            transform={"time_dimension": "year", "filter_dimensions": ["sex"]},
            filter_values={"sex": ["F", "M"]},
        )

    def test_flat_bare_filter_applies_to_both(self):
        # The trap fix: ?sex=M with no sex2 filters BOTH systems, not just sys1.
        fv1, fv2 = extract_filter_pair(self._flat(), {"sex": "M"})
        assert fv1 == {"sex": "M"} and fv2 == {"sex": "M"}

    def test_flat_suffix_overrides_system2(self):
        fv1, fv2 = extract_filter_pair(self._flat(), {"sex": "M", "sex2": "F"})
        assert fv1 == {"sex": "M"} and fv2 == {"sex": "F"}

    def test_hive_bare_filter_inherited_not_defaulted(self):
        # Regression: system 2 must inherit granularity=weekly, not snap to the
        # daily default — else bare ?granularity=weekly compares weekly vs daily.
        fv1, fv2 = extract_filter_pair(hive_dataset(), {"granularity": "weekly"})
        assert fv1 == {"ngram_size": 1, "granularity": "weekly"}
        assert fv2 == {"ngram_size": 1, "granularity": "weekly"}

    def test_hive_partial_override_inherits_rest(self):
        fv1, fv2 = extract_filter_pair(
            hive_dataset(), {"granularity": "weekly", "ngram_size2": "2"})
        assert fv1 == {"ngram_size": 1, "granularity": "weekly"}
        assert fv2 == {"ngram_size": 2, "granularity": "weekly"}


class TestRequireTypesCounts:
    def test_types_counts_passes(self):
        ds = make_dataset_obj(
            "/data", endpoint_schema={"type": "types-counts", "count_column": "pv_count"})
        require_types_counts(ds)  # no raise

    def test_other_endpoint_type_raises_400(self):
        ds = make_dataset_obj("/data")  # conftest default: time-series
        with pytest.raises(HTTPException) as exc:
            require_types_counts(ds)
        assert exc.value.status_code == 400


class TestDatesMode:
    def test_time_dimension_parquet_is_range(self):
        ds = make_dataset_obj("/data", transform={"time_dimension": "date"})
        assert dates_mode(ds) == "range"

    def test_mongodb_is_single(self):
        ds = make_dataset_obj(
            "db/coll", data_format="mongodb", transform={"time_dimension": "time"})
        assert dates_mode(ds) == "single"

    def test_no_time_dimension_is_none(self):
        ds = make_dataset_obj("/data", transform={"filter_dimensions": ["town"]})
        assert dates_mode(ds) == "none"


class TestRequireDatesSupported:
    def test_dates_on_dateless_raises_400(self):
        ds = make_dataset_obj("/data", transform={"filter_dimensions": ["town"]})
        with pytest.raises(HTTPException) as exc:
            require_dates_supported(ds, "vt-zoning-atlas/ngrams", "2020-01-01", None)
        assert exc.value.status_code == 400
        assert "no time dimension" in exc.value.detail

    def test_no_dates_on_dateless_passes(self):
        ds = make_dataset_obj("/data", transform={"filter_dimensions": ["town"]})
        require_dates_supported(ds, "vt-zoning-atlas/ngrams", None, None)

    def test_dates_on_timed_dataset_passes(self):
        ds = make_dataset_obj("/data", transform={"time_dimension": "date"})
        require_dates_supported(ds, "wikimedia/ngrams", "2024-01-01,2024-01-31", None)


class TestRequireSingleDates:
    def test_single_dates_pass(self):
        require_single_dates([("dates", "2024-01-01"), ("dates2", "2024-01-02")])

    def test_range_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            require_single_dates([("dates", "2024-01-01,2024-01-31")])
        assert exc.value.status_code == 400

    def test_missing_required_raises_400(self):
        with pytest.raises(HTTPException):
            require_single_dates([("dates2", None)])

    def test_missing_optional_passes(self):
        require_single_dates([("dates2", None)], required=False)


class TestAvailabilityRangeFor:
    """availability_range_for backs the undated-request clamp: (min, max) for a
    slice so the fallback scan is bounded instead of walking the whole tree."""

    def _ds(self, availability):
        from tests.conftest import make_dataset_obj
        ds = make_dataset_obj("/data")
        ds.manifest = {"availability": availability}
        return ds

    def test_reddit_style_nlang(self):
        from app.core.query_utils import availability_range_for
        ds = self._ds({"1": {"en": {"min": "2010-01-01", "max": "2022-12-31"}}})
        assert availability_range_for(ds, None, {"n": 1, "lang": "en"}) == (
            "2010-01-01", "2022-12-31")

    def test_wikimedia_style_entity_first(self):
        from app.core.query_utils import availability_range_for
        ds = self._ds({"United States": {"1": {"daily": {"min": "2015-01-01", "max": "2026-04-20"}}}})
        assert availability_range_for(
            ds, "United States", {"ngram_size": 1, "granularity": "daily"}) == (
            "2015-01-01", "2026-04-20")

    def test_absent_is_none_pair(self):
        from app.core.query_utils import availability_range_for
        assert availability_range_for(self._ds({}), None, {}) == (None, None)


class TestWidestAvailability:
    """_widest_availability spans primary + type-first form (independent
    pipelines), so a fresh sparkline never truncates the clamp range."""

    def _obj(self, lo, hi):
        from types import SimpleNamespace
        return SimpleNamespace(manifest={"availability": {"min": lo, "max": hi}})

    def test_widest_across_both(self):
        from app.core.term_series import _widest_availability
        primary = self._obj("2015-01-01", "2026-01-01")   # lags
        sparkline = self._obj("2015-06-01", "2026-04-20")  # fresher max
        assert _widest_availability(primary, sparkline, None, {}) == (
            "2015-01-01", "2026-04-20")

    def test_primary_only(self):
        from app.core.term_series import _widest_availability
        assert _widest_availability(self._obj("2015-01-01", "2026-01-01"), None, None, {}) == (
            "2015-01-01", "2026-01-01")
