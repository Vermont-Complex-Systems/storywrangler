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


def _static_openapi() -> "dict | None":
    """Build the spec from the backend app directly — no server, no DB.

    Works when the backend package is importable, e.g.:
        uv run --project backend --with pytest pytest packages/sdk/tests/
    This is the path CI should use so the drift guard never silently skips.
    """
    try:
        from app.main import app
    except ImportError:
        return None
    return app.openapi()


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
        spec = _static_openapi()
        if spec is not None:
            return spec
        pytest.skip(
            f"API not reachable at {STORYWRANGLER_URL} and backend not importable "
            f"(run via: uv run --project backend --with pytest pytest packages/sdk/tests/)"
        )


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


class TestWordshiftDrift:
    def test_sdk_covers_all_api_params(self, openapi_spec):
        """Every API query param should exist in the SDK method (or in **kwargs)."""
        from storywrangler.client import DatasetClient

        api_params = _openapi_query_params(openapi_spec, "/storywrangler/wordshift")
        sdk_params = _sdk_params(DatasetClient.wordshift)
        uncovered = api_params - sdk_params - _SERVER_ONLY_PARAMS
        core_uncovered = {p for p in uncovered if not _is_filter_dim(p)}
        assert not core_uncovered, (
            f"API has query params not in SDK wordshift() signature: {core_uncovered}. "
            f"Add them as explicit params or document why they flow through **filter_dims."
        )

    def test_sdk_params_exist_in_api(self, openapi_spec):
        """Every SDK fixed param should exist in the API spec."""
        from storywrangler.client import DatasetClient

        api_params = _openapi_query_params(openapi_spec, "/storywrangler/wordshift")
        sdk_params = _sdk_params(DatasetClient.wordshift)
        extra = sdk_params - api_params - _SERVER_ONLY_PARAMS
        assert not extra, (
            f"SDK wordshift() has params not in OpenAPI spec: {extra}. "
            f"The API may have removed them."
        )


class TestRouteCoverage:
    """Every registry/auth/instrument route must map to an SDK method.

    The SDK mirrors API routes one-to-one (Label Studio style) so users can
    guess method names from the URL. When this test fails, either add the
    missing SDK method or record the route in ROUTE_MAP with its new method.
    """

    # path → (client class name, method or property name).
    # Bespoke routes map to the Storywrangler.get() escape hatch until they
    # earn a dedicated method.
    ROUTE_MAP = {
        "/registry/register": ("RegistryClient", "register"),
        "/registry/": ("RegistryClient", "list"),
        "/registry/domains": ("RegistryClient", "domains"),
        "/registry/{domain}/{dataset_id}": ("RegistryClient", "get"),
        "/registry/{domain}/{dataset_id}/adapter": ("RegistryClient", "adapter"),
        "/registry/{domain}/{dataset_id}/versions": ("RegistryClient", "versions"),
        "/registry/{domain}/{dataset_id}/validate-sources": ("RegistryClient", "validate_sources"),
        "/admin/registry/{domain}/{dataset_id}/entities": ("RegistryClient", "upsert_entities"),
        "/admin/registry/{domain}/{dataset_id}": ("RegistryClient", "delete"),
        "/auth/login": ("Storywrangler", "login"),
        "/auth/me": ("UsersClient", "whoami"),
        "/admin/auth/users": ("UsersClient", "list"),  # + create() for POST
        "/admin/auth/users/{user_id}/role": ("UsersClient", "set_role"),
        "/storywrangler/top-ngrams": ("InstrumentClient", "top_ngrams"),
        "/storywrangler/allotax": ("InstrumentClient", "allotax"),
        "/storywrangler/rtd": ("InstrumentClient", "rtd"),
        "/storywrangler/wordshift": ("InstrumentClient", "wordshift"),
        # Domain roots — GET /{domain} lists endpoints + datasets
        "/babynames": ("DatasetClient", "endpoints"),
        "/storywrangler": ("DatasetClient", "endpoints"),
        "/reddit": ("DatasetClient", "endpoints"),
        "/wikimedia": ("DatasetClient", "endpoints"),
        "/open-academic-analytics": ("DatasetClient", "endpoints"),
        "/scisciDB": ("DatasetClient", "endpoints"),
        "/twitter": ("DatasetClient", "endpoints"),
        "/vt-zoning-atlas": ("DatasetClient", "endpoints"),
        # Twitter (mongodb pass-through, bespoke router mirroring the generic shapes)
        "/twitter/term-series": ("DatasetClient", "term_series"),
        "/twitter/term-series/batch": ("DatasetClient", "term_series_batch"),
        # Platform
        "/version": ("Storywrangler", "version"),
        "/health/status": ("HealthClient", "status"),
        "/health/status/history": ("HealthClient", "history"),
        "/health/status/{domain}/{dataset_id}": ("HealthClient", "dataset"),
        # Data endpoints — generic DatasetClient methods, domain-bound
        # (top-ngrams is served by the generic /storywrangler/top-ngrams for
        # every domain; babynames and vt-zoning-atlas have no bespoke routes)
        "/wikimedia/term-series": ("DatasetClient", "term_series"),
        "/wikimedia/term-series/batch": ("DatasetClient", "term_series_batch"),
        "/reddit/term-series": ("DatasetClient", "term_series"),
        "/reddit/term-series/batch": ("DatasetClient", "term_series_batch"),
        "/bluesky/term-series": ("DatasetClient", "term_series"),
        "/bluesky/term-series/batch": ("DatasetClient", "term_series_batch"),
        # Bespoke routes — served via the escape hatch for now
        "/wikimedia/precomputed-rtd": ("Storywrangler", "get"),
        "/wikimedia/revisions": ("Storywrangler", "get"),
        "/wikimedia/revisions/{identifier}": ("Storywrangler", "get"),
        "/wikimedia/semantic-ngrams": ("Storywrangler", "get"),
        "/wikimedia/semantic-timeseries": ("Storywrangler", "get"),
        "/scisciDB/metrics": ("Storywrangler", "get"),
        "/open-academic-analytics/academic-research-groups": ("Storywrangler", "get"),
        "/open-academic-analytics/authors": ("Storywrangler", "get"),
        "/open-academic-analytics/coauthors/{author_name}": ("Storywrangler", "get"),
        "/open-academic-analytics/embeddings": ("Storywrangler", "get"),
        "/open-academic-analytics/papers/{author_name}": ("Storywrangler", "get"),
        "/open-academic-analytics/training/{author_name}": ("Storywrangler", "get"),
    }

    # Routes intentionally without an SDK method
    _EXEMPT = {"/"}  # API root banner

    def test_every_route_has_an_sdk_method(self, openapi_spec):
        api_paths = set(openapi_spec.get("paths", {})) - self._EXEMPT
        unmapped = api_paths - set(self.ROUTE_MAP)
        assert not unmapped, (
            f"API routes with no SDK method: {sorted(unmapped)}. "
            f"Add a method mirroring the route name, then record it in ROUTE_MAP."
        )

    def test_mapped_methods_exist(self):
        import storywrangler.client as client_mod

        missing = [
            f"{cls}.{attr} (for {path})"
            for path, (cls, attr) in self.ROUTE_MAP.items()
            if not hasattr(getattr(client_mod, cls), attr)
        ]
        assert not missing, f"ROUTE_MAP points at SDK methods that don't exist: {missing}"


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
