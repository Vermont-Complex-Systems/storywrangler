"""Drift guard: verify SDK method signatures match the API's OpenAPI spec.

Compares the fixed (non-**kwargs) parameters on DatasetClient.allotax() and
DatasetClient.rtd() against the query parameters declared in the OpenAPI spec
for the corresponding endpoints.

Skipped when the API is unreachable (e.g. CI without a running backend).
"""

import inspect
import os

import pytest
import requests

STORYWRANGLER_URL = os.getenv("STORYWRANGLER_URL", "http://localhost:8000")

# SDK params that are injected by the client, not sent as query params
_CLIENT_ONLY_PARAMS = {"self", "filter_dims", "filters"}

# OpenAPI params that the SDK handles implicitly (bound by DatasetClient)
_SERVER_ONLY_PARAMS = {"domain", "dataset"}


def _fetch_openapi() -> dict:
    resp = requests.get(f"{STORYWRANGLER_URL}/openapi.json", timeout=5)
    resp.raise_for_status()
    return resp.json()


def _openapi_query_params(spec: dict, path: str) -> set[str]:
    """Extract query parameter names from the OpenAPI spec for a GET endpoint."""
    endpoint = spec.get("paths", {}).get(path, {}).get("get", {})
    return {
        p["name"]
        for p in endpoint.get("parameters", [])
        if p.get("in") == "query"
    }


def _sdk_params(method) -> set[str]:
    """Extract explicit parameter names from a method signature (excludes **kwargs)."""
    sig = inspect.signature(method)
    return {
        name
        for name, param in sig.parameters.items()
        if param.kind not in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        )
    } - _CLIENT_ONLY_PARAMS


@pytest.fixture(scope="module")
def openapi_spec():
    try:
        return _fetch_openapi()
    except (requests.ConnectionError, requests.Timeout):
        pytest.skip(f"API not reachable at {STORYWRANGLER_URL}")


class TestAllotaxDrift:
    def test_sdk_covers_all_api_params(self, openapi_spec):
        """Every API query param should exist in the SDK method (or in **kwargs)."""
        from storywrangler.client import DatasetClient

        api_params = _openapi_query_params(openapi_spec, "/storywrangler/allotax")
        sdk_params = _sdk_params(DatasetClient.allotax)
        # API params not in SDK fixed signature — these flow through **filter_dims
        uncovered = api_params - sdk_params - _SERVER_ONLY_PARAMS
        # These are expected to be in **filter_dims (dataset-specific)
        # Only flag params that look like core API params (not filter dims)
        core_uncovered = {p for p in uncovered if not _is_filter_dim(p)}
        assert not core_uncovered, (
            f"API has query params not in SDK allotax() signature: {core_uncovered}. "
            f"Add them as explicit params or document why they flow through **filter_dims."
        )

    def test_sdk_params_exist_in_api(self, openapi_spec):
        """Every SDK fixed param should exist in the API spec."""
        from storywrangler.client import DatasetClient

        api_params = _openapi_query_params(openapi_spec, "/storywrangler/allotax")
        sdk_params = _sdk_params(DatasetClient.allotax)
        extra = sdk_params - api_params - _SERVER_ONLY_PARAMS
        assert not extra, (
            f"SDK allotax() has params not in OpenAPI spec: {extra}. "
            f"The API may have removed them."
        )


class TestRtdDrift:
    def test_sdk_covers_all_api_params(self, openapi_spec):
        """Every API query param should exist in the SDK method (or in **kwargs)."""
        from storywrangler.client import DatasetClient

        api_params = _openapi_query_params(openapi_spec, "/storywrangler/rtd")
        sdk_params = _sdk_params(DatasetClient.rtd)
        uncovered = api_params - sdk_params - _SERVER_ONLY_PARAMS
        core_uncovered = {p for p in uncovered if not _is_filter_dim(p)}
        assert not core_uncovered, (
            f"API has query params not in SDK rtd() signature: {core_uncovered}. "
            f"Add them as explicit params or document why they flow through **filters."
        )

    def test_sdk_params_exist_in_api(self, openapi_spec):
        """Every SDK fixed param should exist in the API spec."""
        from storywrangler.client import DatasetClient

        api_params = _openapi_query_params(openapi_spec, "/storywrangler/rtd")
        sdk_params = _sdk_params(DatasetClient.rtd)
        extra = sdk_params - api_params - _SERVER_ONLY_PARAMS
        assert not extra, (
            f"SDK rtd() has params not in OpenAPI spec: {extra}. "
            f"The API may have removed them."
        )


def _is_filter_dim(name: str) -> bool:
    """Heuristic: dataset-specific filter dims are short lowercase names.

    Core API params (entity, dates, alpha, etc.) are handled explicitly.
    Filter dims (granularity, ngram_size, n, lang, sex, etc.) flow through **kwargs.
    This returns True for names that are plausibly filter dims.
    """
    # Known filter dim patterns — extend as new datasets are added
    _KNOWN_FILTER_DIMS = {
        "granularity", "ngram_size", "n", "lang", "sex",
        "granularity2", "ngram_size2", "n2", "lang2", "sex2",
    }
    return name in _KNOWN_FILTER_DIMS
