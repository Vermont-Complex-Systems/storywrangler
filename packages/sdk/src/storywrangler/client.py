"""
Storywrangler client — API wrapper with dataset-scoped instruments.

Usage::

    from storywrangler import Storywrangler
    client = Storywrangler()  # no key needed for reading; api_key= to register

    # Dataset-scoped client (recommended)
    wiki = client.dataset("wikimedia", "ngrams")
    wiki.filters        # discover available filter dimensions
    wiki.availability   # date ranges per entity
    wiki.adapter        # entity mapping rows (local_id ↔ entity_id ↔ entity_name)

    # Data endpoints — every response has a .df() accessor (pandas extra)
    wiki.top_ngrams(dates="2026-05-01", granularity="daily", ngram_size=1)
    wiki.term_series("hello", entity="wikidata:Q30", window=30).df()
    wiki.term_series_batch(["hello", "world"], entity="wikidata:Q30").df()

    result = wiki.allotax(
        entity="wikidata:Q30", entity2="wikidata:Q145",
        dates="2026-05-01", dates2="2026-05-01",
        ngram_size=1, granularity="daily",
    )

    # Domain-scoped: displaying the client lists the endpoints (GET /{domain})
    wiki = client.dataset("wikimedia")
    wiki                    # renders the endpoint list + registered datasets
    wiki.term_series(...)   # data endpoints work; metadata needs a dataset id

    # Any domain route is callable by its guessable name (dynamic mirror)
    wiki.revisions(limit=10)
    wiki.semantic_ngrams(...)

    # Routes outside a domain client
    client.get("/open-academic-analytics/authors")

    # Flat API (still available)
    result = client.instrument.allotax(
        domain="wikimedia", dataset="ngrams",
        entity="wikidata:Q30", entity2="wikidata:Q145",
        dates="2026-05-01", dates2="2026-05-01",
        ngram_size=1, granularity="daily",
    )
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from storywrangler_schemas.coercion import coerce_scalar

from .registry.models import DatasetCreate, EntityRow

load_dotenv()


def _require_pandas():
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(
            ".df() requires pandas — install with: pip install 'storywrangler[pandas]'"
        ) from e
    return pd


class DataResponse(dict):
    """API response dict with a ``.df()`` accessor.

    Behaves exactly like the raw response dict; ``.df()`` converts the tabular
    payload to a pandas DataFrame (requires the ``pandas`` extra).
    """

    def df(self):
        """Return the tabular part of this response as a pandas DataFrame.

        Looks for a ``data`` or ``series`` payload first, then falls back to
        any top-level list-of-records values (multiple lists — e.g. a
        dates/dates2 comparison — are concatenated with a ``system`` column;
        a ``term → rows`` mapping gains a ``type`` column).
        """
        pd = _require_pandas()

        def records(val):
            return isinstance(val, list) and (not val or isinstance(val[0], dict))

        for key in ("data", "series"):
            val = self.get(key)
            if records(val):
                return pd.DataFrame(val)
            if isinstance(val, dict):  # batch shape: term → rows
                frames = [
                    pd.DataFrame(rows).assign(type=term)
                    for term, rows in val.items() if records(rows)
                ]
                if frames:
                    return pd.concat(frames, ignore_index=True)

        tables = {k: v for k, v in self.items() if records(v) and v}
        if len(tables) == 1:
            return pd.DataFrame(next(iter(tables.values())))
        if len(tables) > 1:  # e.g. dual-system top-ngrams keyed by date range
            return pd.concat(
                [pd.DataFrame(v).assign(system=k) for k, v in tables.items()],
                ignore_index=True,
            )
        raise ValueError(
            f"No tabular payload found in this response (keys: {sorted(self)})."
        )


class RecordList(list):
    """API response list with a ``.df()`` accessor."""

    def df(self):
        return _require_pandas().DataFrame(self)


def _wrap(payload):
    """Give JSON payloads a .df() accessor without changing their behavior."""
    if isinstance(payload, dict):
        return DataResponse(payload)
    if isinstance(payload, list):
        return RecordList(payload)
    return payload


def _instrument_params(
    domain: str, dataset: str, alpha, ngram_limit: int, wordshift_limit: int,
    **optional,
) -> Dict[str, Any]:
    """Build query params for instrument endpoints, dropping None optionals."""
    params: Dict[str, Any] = {
        "domain": domain, "dataset": dataset,
        "alpha": str(alpha),
        "ngram_limit": ngram_limit, "wordshift_limit": wordshift_limit,
    }
    params.update({k: v for k, v in optional.items() if v is not None})
    return params


class _SubClient:
    """Base class for sub-resource clients — shares the parent session."""

    def __init__(self, session: requests.Session, base_url: str, timeout: int = 300) -> None:
        self._session = session
        self._base_url = base_url
        self._timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _get(self, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return self._session.get(self._url(path), **kwargs)

    def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = self._get(path, params=params)
        resp.raise_for_status()
        return _wrap(resp.json())

    def _post(self, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return self._session.post(self._url(path), **kwargs)

    def _put(self, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return self._session.put(self._url(path), **kwargs)

    def _delete(self, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return self._session.delete(self._url(path), **kwargs)


class RegistryClient(_SubClient):
    """Interact with /registry endpoints.

    Method-per-route (Label Studio style)::

        POST /registry/register                        → register(payload)
        GET  /registry/                                → list()
        GET  /registry/domains                         → domains()
        GET  /registry/{domain}/{id}                   → get(domain, id, full=, version=)
        GET  /registry/{domain}/{id}/adapter           → adapter(domain, id)
        GET  /registry/{domain}/{id}/versions          → versions(domain, id)
        GET  /registry/{domain}/{id}/validate-sources  → validate_sources(domain, id)
        POST /admin/registry/{domain}/{id}/entities    → upsert_entities(domain, id, rows)
        DELETE /admin/registry/{domain}/{id}           → delete(domain, id)
    """

    def register(self, payload: "DatasetCreate | dict") -> bool:
        """Register or update a dataset (upsert). Returns True on success."""
        if not isinstance(payload, DatasetCreate):
            payload = DatasetCreate.model_validate(payload)
        dataset_id = payload.dataset_id
        try:
            resp = self._post(
                "/registry/register",
                json=payload.model_dump(mode="json", exclude_none=True),
            )
            if resp.status_code in (200, 201):
                print(f"  {dataset_id} registered successfully!")
                return True
            print(f"  {dataset_id} failed: {resp.status_code}")
            print(f"    {resp.text[:500]}")
            return False
        except requests.exceptions.ConnectionError:
            print(f"  Could not connect to {self._base_url}")
            return False
        except Exception as e:
            print(f"  Unexpected error: {type(e).__name__}: {e}")
            return False

    def list(self) -> Dict[str, Any]:
        """List all registered datasets."""
        return _wrap(self._get("/registry/").json())

    def __repr__(self) -> str:
        # Displaying the client shows what its root route serves (the catalog),
        # same rule as the domain client. Best-effort — falls back when offline.
        try:
            datasets = self.list().get("datasets", [])
        except Exception:
            return "RegistryClient()"
        lines = [f"Registry — {len(datasets)} datasets:"]
        for ds in datasets:
            ident = f"{ds.get('domain')}/{ds.get('dataset_id')}"
            desc = (ds.get("description") or "").split("\n")[0]
            if len(desc) > 60:
                desc = desc[:57] + "..."
            lines.append(f"  {ident:36} {ds.get('version', ''):8} {desc}")
        lines.append("use .list().df() for a table, .get(domain, id) for one dataset")
        return "\n".join(lines)

    def domains(self) -> Dict[str, Any]:
        """List accepted domain names for dataset registration."""
        return self._get_json("/registry/domains")

    def get(
        self, domain: str, dataset_id: str,
        full: bool = False, version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get metadata for a specific dataset.

        Defaults to the latest version. Pass ``version="1.0.0"`` for an
        immutable snapshot; ``full=True`` includes partition_index.
        """
        params: Dict[str, Any] = {"full": full}
        if version is not None:
            params["version"] = version
        return _wrap(self._get(f"/registry/{domain}/{dataset_id}", params=params).json())

    def adapter(self, domain: str, dataset_id: str) -> List[Dict[str, Any]]:
        """Entity mapping rows for a dataset (local_id ↔ entity_id ↔ entity_name).

        Returns::

            [{'local_id': 'united_states', 'entity_id': 'wd:Q30',
              'entity_name': 'United States', 'entity_ids': ['wd:Q30']}, ...]

        Raises ``requests.HTTPError`` (404) if the dataset has no entity mappings.
        """
        resp = self._get(f"/registry/{domain}/{dataset_id}/adapter")
        resp.raise_for_status()
        return _wrap(resp.json())

    def versions(self, domain: str, dataset_id: str) -> Dict[str, Any]:
        """List all registered versions for a dataset, newest first."""
        return self._get_json(f"/registry/{domain}/{dataset_id}/versions")

    def validate_sources(self, domain: str, dataset_id: str) -> Dict[str, Any]:
        """Check that the dataset's lineage source URLs are still accessible."""
        return self._get_json(f"/registry/{domain}/{dataset_id}/validate-sources")

    def upsert_entities(
        self, domain: str, dataset_id: str,
        entities: List["EntityRow | dict"],
    ) -> Dict[str, Any]:
        """Batch upsert entity mapping rows for a registered dataset (admin only).

        Idempotent — existing local_ids are updated, new ones inserted.
        """
        rows = [
            e.model_dump(mode="json") if isinstance(e, EntityRow)
            else EntityRow.model_validate(e).model_dump(mode="json")
            for e in entities
        ]
        resp = self._post(f"/admin/registry/{domain}/{dataset_id}/entities", json=rows)
        resp.raise_for_status()
        return resp.json()

    def delete(self, domain: str, dataset_id: str) -> Dict[str, Any]:
        """Retire a dataset (admin only): removes all registry versions and
        entity mappings. Data on disk is untouched — the dataset can be
        re-registered at any time.
        """
        resp = self._delete(f"/admin/registry/{domain}/{dataset_id}")
        resp.raise_for_status()
        return resp.json()


class InstrumentClient(_SubClient):
    """Interact with /storywrangler instrument endpoints."""

    def allotax(
        self,
        domain: str = "wikimedia",
        dataset: str = "ngrams",
        *,
        entity: str | None = None,
        entity2: str | None = None,
        dates: str | None = None,
        dates2: str | None = None,
        alpha: str | float = "1.0",
        alphas: str | None = None,
        weight: str | None = None,
        ngram_limit: int = 10000,
        wordshift_limit: int = 200,
        **filter_dims,
    ) -> Dict[str, Any]:
        """Run the allotaxonometer (rank-turbulence divergence) on two systems.

        Args:
            domain: Dataset domain.
            dataset: Dataset ID.
            entity/entity2: Global entity IDs (e.g. 'wikidata:Q30').
            dates/dates2: Date ranges ('2024-10-01' or '2024-10-01,2024-10-31').
            alpha: RTD alpha parameter (number or 'inf').
            alphas: Comma-separated alphas for multi-alpha mode.
            ngram_limit: Max types to load per system.
            wordshift_limit: Max wordshift entries to return.
            **filter_dims: Dataset-specific filter dimensions passed as query
                params. Use actual column names from the dataset's level_order —
                e.g. ``ngram_size=1, granularity="daily"`` for wikimedia,
                ``n=1, lang="en"`` for reddit, ``sex="M", sex2="F"`` for babynames.

        Returns:
            Dict with normalization, delta_sum, diamond_counts, wordshift, meta, etc.
        """
        params = _instrument_params(
            domain, dataset, alpha, ngram_limit, wordshift_limit,
            entity=entity, entity2=entity2, dates=dates, dates2=dates2, alphas=alphas,
            weight=weight,
        )
        params.update(filter_dims)
        return self._get_json("/storywrangler/allotax", params)

    def rtd(
        self,
        domain: str = "wikimedia",
        dataset: str = "ngrams",
        *,
        entity: str | None = None,
        dates: str | None = None,
        dates2: str | None = None,
        alpha: str | float = "0.25",
        alphas: str | None = None,
        weight: str | None = None,
        ngram_limit: int = 10000,
        wordshift_limit: int = 10000,
        **filters: str,
    ) -> Dict[str, Any]:
        """Lightweight rank-turbulence divergence between two dates.

        Returns per-term signed divergence contributions (wordshift only,
        no diamond plot or balance). Designed for fast comparisons.

        Args:
            domain: Dataset domain.
            dataset: Dataset ID.
            entity: Global entity ID.
            dates/dates2: Target and reference dates.
            alpha: RTD alpha parameter.
            alphas: Comma-separated alphas for multi-alpha mode.
            ngram_limit: Max types to load per system.
            wordshift_limit: Max wordshift entries to return.
            **filters: Dataset-specific filter dimensions passed as query
                params. Use actual column names from the dataset's level_order.
        """
        params = _instrument_params(
            domain, dataset, alpha, ngram_limit, wordshift_limit,
            entity=entity, dates=dates, dates2=dates2, alphas=alphas,
            weight=weight,
        )
        params.update(filters)
        return self._get_json("/storywrangler/rtd", params)


class HealthClient(_SubClient):
    """Interact with /health endpoints.

    Method-per-route (Label Studio style)::

        GET /health/status                       → status()
        GET /health/status/history               → history()
        GET /health/status/{domain}/{dataset_id} → dataset(domain, dataset_id)
    """

    def status(self) -> Dict[str, Any]:
        """Latest health check result for every registered dataset."""
        return self._get_json("/health/status")

    def history(self, **params) -> Dict[str, Any]:
        """Health check history across datasets."""
        return self._get_json("/health/status/history", params or None)

    def dataset(self, domain: str, dataset_id: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """Health check history for one dataset."""
        params = {"limit": limit} if limit is not None else None
        return self._get_json(f"/health/status/{domain}/{dataset_id}", params)


class UsersClient(_SubClient):
    """Interact with /auth and /admin/auth endpoints.

    Method-per-route (Label Studio style)::

        GET  /auth/me                        → whoami()
        GET  /admin/auth/users               → list()
        POST /admin/auth/users               → create(username, email, password, role=)
        PUT  /admin/auth/users/{id}/role     → set_role(user_id, role)
    """

    def whoami(self) -> Dict[str, Any]:
        """Return the current user's profile."""
        return self._get_json("/auth/me")

    def list(self) -> List[Dict[str, Any]]:
        """List all user accounts (admin only)."""
        resp = self._get("/admin/auth/users")
        resp.raise_for_status()
        return _wrap(resp.json())

    def create(
        self, username: str, email: str, password: str, role: str = "user",
    ) -> Dict[str, Any]:
        """Create a user account (admin only). The response includes the generated API key."""
        resp = self._post(
            "/admin/auth/users",
            json={"username": username, "email": email, "password": password, "role": role},
        )
        resp.raise_for_status()
        return resp.json()

    def set_role(self, user_id: int, role: str) -> Dict[str, Any]:
        """Promote or demote a user to 'admin' or 'user' (admin only)."""
        resp = self._put(f"/admin/auth/users/{user_id}/role", params={"role": role})
        resp.raise_for_status()
        return resp.json()


class DatasetClient(_SubClient):
    """A dataset-scoped client with filter discovery and instrument methods.

    Lazily fetches registry metadata on first property access and caches it.

    Example::

        wiki = client.dataset("wikimedia", "ngrams")
        wiki.filters
        # {'ngram_size': {'default': 1, 'valid': [1, 2]},
        #  'granularity': {'default': 'daily', 'valid': ['daily', 'weekly', 'monthly']}}

        result = wiki.allotax(
            entity="wikidata:Q30", entity2="wikidata:Q145",
            dates="2026-05-01", dates2="2026-05-01",
            ngram_size=1, granularity="daily",
        )
    """

    def __init__(
        self, session: requests.Session, base_url: str, timeout: int,
        domain: str, dataset_id: Optional[str] = None,
    ) -> None:
        super().__init__(session, base_url, timeout)
        self.domain = domain
        self.dataset_id = dataset_id
        self._meta: Optional[Dict[str, Any]] = None
        self._meta_cache: Dict[str, Dict[str, Any]] = {}
        self._adapter: Optional[List[Dict[str, Any]]] = None
        self._domain_info: Optional[Dict[str, Any]] = None
        self._instrument = InstrumentClient(session, base_url, timeout)
        self._registry = RegistryClient(session, base_url, timeout)

    def _domain_root(self) -> Dict[str, Any]:
        """GET /{domain} — the domain's endpoints and registered datasets (cached)."""
        if self._domain_info is None:
            self._domain_info = self._get_json(f"/{self.domain}")
        return self._domain_info

    def _resolve_dataset_id(self) -> str:
        """The bound dataset id, resolving it for single-dataset domains.

        Raises a teaching error when the domain has several datasets and none
        was passed — dataset-specific surfaces need an explicit choice.
        """
        if self.dataset_id is None:
            datasets = self._domain_root().get("datasets", [])
            if len(datasets) == 1:
                self.dataset_id = datasets[0]
            else:
                raise ValueError(
                    f"This is dataset-specific and domain '{self.domain}' has "
                    f"{len(datasets)} registered datasets — use "
                    f"client.dataset('{self.domain}', <id>) with id in {datasets}."
                )
        return self.dataset_id

    def _fetch_meta(self, dataset_id: str) -> Dict[str, Any]:
        """Registry metadata for one dataset in this domain (cached per id)."""
        if dataset_id not in self._meta_cache:
            resp = self._get(f"/registry/{self.domain}/{dataset_id}")
            if resp.status_code == 404:
                # Fail fast with choices instead of a bare HTTP 404.
                try:
                    ids = self._domain_root().get("datasets", [])
                except Exception:
                    ids = []
                hint = f"registered: {ids}" if ids else "no datasets registered in this domain"
                raise ValueError(
                    f"Unknown dataset '{dataset_id}' in domain '{self.domain}' — {hint}."
                )
            resp.raise_for_status()
            self._meta_cache[dataset_id] = _wrap(resp.json())
        return self._meta_cache[dataset_id]

    def _ensure_meta(self) -> Dict[str, Any]:
        if self._meta is None:
            self._meta = self._fetch_meta(self._resolve_dataset_id())
        return self._meta

    def _check_route(self, path: str) -> None:
        """Raise before sending when the domain doesn't serve *path*.

        Generic data methods exist on every DatasetClient, but not every
        domain serves every route — this turns a bare 404 into an actionable
        error. Best-effort: skipped when the OpenAPI spec can't be fetched.
        """
        try:
            known = self.endpoints
        except Exception:
            return
        if known and path not in known:
            available = ", ".join(sorted(known))
            raise ValueError(
                f"'{self.domain}' has no {path} endpoint. Available: {available}. "
                f"Use .endpoints to discover routes."
            )

    def refresh(self) -> "DatasetClient":
        """Clear cached metadata so the next access re-fetches from the registry."""
        self._meta = None
        self._meta_cache = {}
        self._adapter = None
        self._domain_info = None
        return self

    @property
    def meta(self) -> Dict[str, Any]:
        """Full registry metadata for this dataset (cached after first access)."""
        return self._ensure_meta()

    @property
    def filters(self) -> Dict[str, Dict[str, Any]]:
        """Available filter dimensions with defaults and valid values.

        Returns::

            {'ngram_size': {'default': 1, 'valid': [1, 2]},
             'granularity': {'default': 'daily', 'valid': ['daily', 'weekly', 'monthly']}}
        """
        return self._filters_from_meta(self._ensure_meta())

    @staticmethod
    def _filters_from_meta(meta: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        level_order: List[Dict[str, Any]] = meta.get("level_order") or []
        filter_values: Dict[str, list] = meta.get("filter_values") or {}
        if level_order:
            return {
                level["column"]: {
                    "default": level.get("default_value"),
                    "valid": filter_values.get(level["column"], []),
                }
                for level in level_order
                if level.get("type") in ("partition", "filter")
            }
        # Flat parquet has no hive levels — fall back to the introspected
        # filter_values (populated from transform.filter_dimensions), so
        # filter validation still works. Defaults are server-side only here.
        return {
            col: {"default": None, "valid": vals}
            for col, vals in filter_values.items()
        }

    @property
    def availability(self) -> Dict[str, Any]:
        """Date ranges per entity from manifest.availability."""
        return (self._ensure_meta().get("manifest") or {}).get("availability", {})

    @property
    def adapter(self) -> List[Dict[str, Any]]:
        """Entity mapping rows (local_id ↔ entity_id ↔ entity_name), cached.

        Returns ``[]`` for datasets without entity mappings. Use these rows to
        translate between global entity IDs (``wd:Q30``) and the dataset-local
        values stored on disk.
        """
        if self._adapter is None:
            resp = self._get(f"/registry/{self.domain}/{self.dataset_id}/adapter")
            if resp.status_code == 404:
                self._adapter = RecordList()
            else:
                resp.raise_for_status()
                self._adapter = _wrap(resp.json())
        return self._adapter

    @property
    def endpoints(self) -> Dict[str, Dict[str, Any]]:
        """The domain's routes, from GET /{domain} (cached).

        Returns ``{path: {"summary": ..., "dataset": ...}}`` where ``dataset``
        is the registered dataset the route serves (its ``x-dataset``
        declaration), e.g.::

            {'/wikimedia/term-series': {'summary': 'Term Series', 'dataset': 'ngrams'}, ...}

        Note: routes are per-domain, and the platform instruments
        (``/storywrangler/allotax``, ``/storywrangler/rtd``) work for every
        dataset — reach them via :meth:`allotax` and :meth:`rtd`.
        """
        return self._domain_root().get("endpoints", {})

    @property
    def datasets(self) -> List[str]:
        """Dataset ids registered under this domain, from GET /{domain}."""
        return self._domain_root().get("datasets", [])

    @property
    def description(self) -> Optional[str]:
        """Dataset description."""
        return self._ensure_meta().get("description")

    def _validate_filters(self, filter_dims: Dict[str, Any], path: Optional[str] = None) -> None:
        """Validate filter kwargs against registry metadata.

        Validates against the dataset the route declares (its ``x-dataset``
        annotation) when *path* is given and annotated; otherwise against the
        bound dataset. Raises ValueError with actionable messages when:
        - A filter name is not a known dimension for this dataset.
        - A filter value is not in the set of valid values.
        """
        meta = None
        label = f"{self.domain}/{self.dataset_id}"
        if path is not None:
            try:
                route_ds = (self.endpoints.get(path) or {}).get("dataset")
                if route_ds:
                    meta = self._fetch_meta(route_ds)
                    label = f"{self.domain}/{route_ds}"
            except Exception:
                meta = None
        if meta is None:
            if self.dataset_id is None:
                # Domain mode with an unannotated route — let the server decide.
                return
            meta = self._ensure_meta()
        known = self._filters_from_meta(meta)
        if not known:
            return  # no metadata yet — skip validation, let server decide

        for key, val in filter_dims.items():
            # Strip trailing "2" suffix (e.g. sex2 → sex) for system-2 dims
            base_key = key.rstrip("2") if key.endswith("2") and key[:-1] in known else key
            if base_key not in known:
                available = ", ".join(sorted(known))
                raise ValueError(
                    f"Unknown filter '{key}' for {label}. "
                    f"Available filters: [{available}]. "
                    f"Use .filters to see valid values."
                )
            valid = known[base_key].get("valid", [])
            if valid:
                # Try type coercion (query params are often strings)
                coerced = coerce_scalar(val)
                if val not in valid and coerced not in valid:
                    valid_str = ", ".join(str(v) for v in sorted(valid, key=str))
                    raise ValueError(
                        f"Invalid value '{val}' for filter '{key}' "
                        f"on {label}. "
                        f"Valid values: [{valid_str}]. "
                        f"Use .filters to see defaults."
                    )

    def allotax(
        self,
        *,
        entity: str | None = None,
        entity2: str | None = None,
        dates: str | None = None,
        dates2: str | None = None,
        alpha: str | float = "1.0",
        alphas: str | None = None,
        weight: str | None = None,
        ngram_limit: int = 10000,
        wordshift_limit: int = 200,
        **filter_dims,
    ) -> Dict[str, Any]:
        """Run the allotaxonometer on this dataset.

        Same as ``client.instrument.allotax()`` but ``domain`` and ``dataset``
        are already bound.

        Args:
            entity/entity2: Global entity IDs (e.g. 'wikidata:Q30').
            dates/dates2: Date ranges ('2024-10-01' or '2024-10-01,2024-10-31').
            alpha: RTD alpha parameter (number or 'inf').
            alphas: Comma-separated alphas for multi-alpha mode.
            ngram_limit: Max types to load per system.
            wordshift_limit: Max wordshift entries to return.
            **filter_dims: Dataset-specific filters (e.g. ngram_size=1).

        Raises:
            ValueError: If a filter name is unknown or a value is invalid.
                Use ``.filters`` to discover available dimensions.
        """
        self._resolve_dataset_id()
        self._validate_filters(filter_dims)
        return self._instrument.allotax(
            self.domain, self.dataset_id,
            entity=entity, entity2=entity2, dates=dates, dates2=dates2,
            alpha=alpha, alphas=alphas, weight=weight,
            ngram_limit=ngram_limit, wordshift_limit=wordshift_limit,
            **filter_dims,
        )

    def rtd(
        self,
        *,
        entity: str | None = None,
        dates: str | None = None,
        dates2: str | None = None,
        alpha: str | float = "0.25",
        alphas: str | None = None,
        weight: str | None = None,
        ngram_limit: int = 10000,
        wordshift_limit: int = 10000,
        **filters: str,
    ) -> Dict[str, Any]:
        """Lightweight rank-turbulence divergence on this dataset.

        Same as ``client.instrument.rtd()`` but ``domain`` and ``dataset``
        are already bound.

        Raises:
            ValueError: If a filter name is unknown or a value is invalid.
                Use ``.filters`` to discover available dimensions.
        """
        self._resolve_dataset_id()
        self._validate_filters(filters)
        return self._instrument.rtd(
            self.domain, self.dataset_id,
            entity=entity, dates=dates, dates2=dates2,
            alpha=alpha, alphas=alphas, weight=weight,
            ngram_limit=ngram_limit, wordshift_limit=wordshift_limit,
            **filters,
        )

    def top_ngrams(
        self,
        *,
        dates: str | None = None,
        dates2: str | None = None,
        entity: str | None = None,
        locations: str | None = None,
        limit: int | None = None,
        **filter_dims,
    ) -> Dict[str, Any]:
        """Top types by count — GET /{domain}/top-ngrams.

        Args:
            dates: Date or range for system 1 ('2024-10-01' or '2024-10-01,2024-10-31').
            dates2: Optional second range for temporal comparison.
            entity: Entity ID (e.g. 'wikidata:Q30') or local ID, where the
                dataset declares an entity_mapping — same convention as
                term_series and the instruments.
            locations: Deprecated alias for ``entity``.
            limit: Max rows to return.
            **filter_dims: Dataset-specific filters (e.g. ``granularity="daily",
                ngram_size=1`` for wikimedia, ``sex="M"`` for babynames). Use
                ``.filters`` to discover them.
        """
        params = {
            k: v for k, v in
            {"dates": dates, "dates2": dates2, "entity": entity,
             "locations": locations, "limit": limit}.items()
            if v is not None
        }
        params.update(filter_dims)
        path = f"/{self.domain}/top-ngrams"
        self._check_route(path)
        self._validate_filters(filter_dims, path=path)
        return self._get_json(path, params)

    def term_series(
        self,
        type: str,
        *,
        entity: str | None = None,
        date: str | None = None,
        window: int | None = None,
        include_articles: bool | None = None,
        sparkline_dataset: str | None = None,
        **filter_dims,
    ) -> Dict[str, Any]:
        """One term's counts over time — GET /{domain}/term-series.

        Args:
            type: The term to look up (e.g. 'hello').
            entity: Global entity ID, where the domain supports entity resolution.
            date: Anchor date; defaults to the latest available.
            window: Days of history around the anchor date (0 = full history).
            include_articles: Attach top articles per date (wikimedia only).
            sparkline_dataset: Override the sparkline source (wikimedia only).
            **filter_dims: Dataset-specific filters (e.g. ``granularity="daily"``).
        """
        params: Dict[str, Any] = {"type": type}
        params.update({
            k: v for k, v in
            {"entity": entity, "date": date, "window": window,
             "include_articles": include_articles, "sparkline_dataset": sparkline_dataset}.items()
            if v is not None
        })
        params.update(filter_dims)
        path = f"/{self.domain}/term-series"
        self._check_route(path)
        self._validate_filters(filter_dims, path=path)
        return self._get_json(path, params)

    def term_series_batch(
        self,
        types: "str | List[str]",
        *,
        entity: str | None = None,
        date: str | None = None,
        window: int | None = None,
        include_articles: bool | None = None,
        articles_dates: str | None = None,
        sparkline_dataset: str | None = None,
        **filter_dims,
    ) -> Dict[str, Any]:
        """Several terms' counts over time — GET /{domain}/term-series/batch.

        Args:
            types: Terms to look up — a list or a comma-separated string.
            (remaining args as in :meth:`term_series`)
        """
        if isinstance(types, (list, tuple)):
            types = ",".join(types)
        params: Dict[str, Any] = {"types": types}
        params.update({
            k: v for k, v in
            {"entity": entity, "date": date, "window": window,
             "include_articles": include_articles, "articles_dates": articles_dates,
             "sparkline_dataset": sparkline_dataset}.items()
            if v is not None
        })
        params.update(filter_dims)
        path = f"/{self.domain}/term-series/batch"
        self._check_route(path)
        self._validate_filters(filter_dims, path=path)
        return self._get_json(path, params)

    def __getattr__(self, name: str):
        """Unknown attributes become domain-route calls (route mirror).

        ``ds.semantic_ngrams(k=2)`` → ``GET /{domain}/semantic-ngrams?k=2`` —
        every route under the domain is callable by its guessable name, even
        before the SDK grows a dedicated method for it. Explicit methods
        (``term_series``, ``top_ngrams``, ...) take precedence and add filter
        validation; dynamic calls are pass-through (kwargs become query
        params, None values dropped). Use ``.endpoints`` to see what exists.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        path = f"/{self.domain}/{name.replace('_', '-')}"

        def _call(**params):
            self._check_route(path)
            return self._get_json(
                path, {k: v for k, v in params.items() if v is not None} or None
            )

        _call.__name__ = name
        _call.__qualname__ = f"DatasetClient.{name}"
        _call.__doc__ = f"GET {path} — dynamic route mirror; kwargs become query params."
        return _call

    def versions(self) -> Dict[str, Any]:
        """List all registered versions of this dataset, newest first."""
        return self._registry.versions(self.domain, self.dataset_id)

    def validate_sources(self) -> Dict[str, Any]:
        """Check that this dataset's lineage source URLs are still accessible."""
        return self._registry.validate_sources(self.domain, self.dataset_id)

    def __repr__(self) -> str:
        if self.dataset_id is not None:
            return f"DatasetClient('{self.domain}/{self.dataset_id}')"
        # Domain mode: displaying the object answers "what can I call here?"
        # (mirrors GET /{domain}). Best-effort — falls back when offline.
        try:
            info = self._domain_root()
        except Exception:
            return f"DatasetClient(domain='{self.domain}')"
        lines = [f"Domain '{self.domain}' — endpoints:"]
        for path, ep in sorted(info.get("endpoints", {}).items()):
            ds = ep.get("dataset")
            served = f"  [serves: {ds}]" if ds else ""
            lines.append(f"  {path:44} {ep.get('summary', '')}{served}")
        datasets = info.get("datasets", [])
        lines.append(
            f"datasets: {datasets} — client.dataset('{self.domain}', <id>) for metadata"
        )
        return "\n".join(lines)


class Storywrangler:
    """Top-level Storywrangler API client.

    Reading data needs no API key — all query endpoints are public. A key is
    only required for registration (`registry.register`, `registry.upsert_entities`)
    and user administration (`users.create`, `users.set_role`, ...).

    Args:
        base_url: API base URL. Defaults to STORYWRANGLER_URL env var or https://api.storywrangler.uvm.edu.
        api_key:  API key (Bearer token). Defaults to API_KEY env var; optional
                  for public endpoints.
        timeout:  Request timeout in seconds. Defaults to 300 (5 min) to
                  accommodate slow parquet introspection over NFS.

    Set STORYWRANGLER_INSECURE=1 to skip TLS verification (self-signed certs).
    """

    def __init__(self, base_url: str = None, api_key: str = None, timeout: int = 300) -> None:
        base_url = (base_url or os.getenv("STORYWRANGLER_URL", "https://api.storywrangler.uvm.edu")).rstrip("/")
        api_key = api_key or os.getenv("API_KEY")
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"
        if os.getenv("STORYWRANGLER_INSECURE") == "1":
            self._session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._base_url = base_url
        self.registry = RegistryClient(self._session, base_url, timeout)
        self.instrument = InstrumentClient(self._session, base_url, timeout)
        self.users = UsersClient(self._session, base_url, timeout)
        self.health = HealthClient(self._session, base_url, timeout)

    def get(self, path: str, **params) -> Any:
        """Raw GET escape hatch for routes without a dedicated method.

        Example::

            client.get("/open-academic-analytics/authors", limit=10)
            client.get("/scisciDB/metrics", group_by="field,year")
        """
        resp = self._session.get(
            f"{self._base_url}{path}", params=params or None, timeout=self._timeout,
        )
        resp.raise_for_status()
        return _wrap(resp.json())

    def version(self) -> Dict[str, Any]:
        """Component versions of the running API (api, schemas, duckdb, allotax)."""
        return self.get("/version")

    def dataset(self, domain: str, dataset_id: Optional[str] = None) -> DatasetClient:
        """Return a domain- or dataset-scoped client (mirrors GET /{domain}).

        With *dataset_id* the client is dataset-scoped: metadata properties
        (``.meta``/``.filters``/``.availability``/``.adapter``) read that
        registry entry. Without it the client is domain-scoped: displaying it
        lists the domain's endpoints (``GET /{domain}``), data endpoints are
        callable as methods, and dataset-specific metadata resolves only when
        the domain has exactly one registered dataset — otherwise it raises
        listing the choices.

        Example::

            wiki = client.dataset("wikimedia")        # domain-scoped
            wiki                                       # shows the endpoint list
            wiki.term_series("hello", entity="wikidata:Q30", window=30)
            wiki = client.dataset("wikimedia", "ngrams")   # dataset-scoped
            wiki.filters   # see available filter dimensions
            wiki.allotax(entity="wikidata:Q30", dates="2026-05-01", ngram_size=1)
        """
        return DatasetClient(self._session, self._base_url, self._timeout, domain, dataset_id)

    @classmethod
    def login(cls, username: str, password: str, base_url: str = None) -> "Storywrangler":
        """Authenticate with username/password and return a configured client.

        Example:
            client = Storywrangler.login("admin", "changethis")
            print(client.users.whoami())
        """
        base_url = (base_url or os.getenv("STORYWRANGLER_URL", "https://api.storywrangler.uvm.edu")).rstrip("/")
        verify = os.getenv("STORYWRANGLER_INSECURE") != "1"
        resp = requests.post(
            f"{base_url}/auth/login",
            json={"username": username, "password": password},
            verify=verify,
        )
        resp.raise_for_status()
        api_key = resp.json()["api_key"]
        return cls(base_url=base_url, api_key=api_key)
