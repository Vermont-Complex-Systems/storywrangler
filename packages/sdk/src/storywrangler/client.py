"""
Storywrangler client — API wrapper with dataset-scoped instruments.

Usage::

    from storywrangler import Storywrangler
    client = Storywrangler(base_url="http://localhost:8000", api_key="<your-key>")

    # Dataset-scoped client (recommended)
    wiki = client.dataset("wikimedia", "ngrams")
    wiki.filters        # discover available filter dimensions
    wiki.availability   # date ranges per entity

    result = wiki.allotax(
        entity="wikidata:Q30", entity2="wikidata:Q145",
        dates="2026-05-01", dates2="2026-05-01",
        ngram_size=1, granularity="daily",
    )

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

from .registry.models import DatasetCreate

load_dotenv()


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
        return resp.json()

    def _post(self, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return self._session.post(self._url(path), **kwargs)

    def _put(self, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return self._session.put(self._url(path), **kwargs)


class RegistryClient(_SubClient):
    """Interact with /registry endpoints."""

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
        return self._get("/registry/").json()

    def get(self, domain: str, dataset_id: str, full: bool = False) -> Dict[str, Any]:
        """Get metadata for a specific dataset."""
        return self._get(f"/registry/{domain}/{dataset_id}", params={"full": full}).json()


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
        )
        params.update(filters)
        return self._get_json("/storywrangler/rtd", params)


class UsersClient(_SubClient):
    """Interact with /auth endpoints."""

    def whoami(self) -> Dict[str, Any]:
        """Return the current user's profile."""
        return self._get_json("/auth/me")


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
        domain: str, dataset_id: str,
    ) -> None:
        super().__init__(session, base_url, timeout)
        self.domain = domain
        self.dataset_id = dataset_id
        self._meta: Optional[Dict[str, Any]] = None
        self._instrument = InstrumentClient(session, base_url, timeout)

    def _ensure_meta(self) -> Dict[str, Any]:
        if self._meta is None:
            self._meta = self._get_json(f"/registry/{self.domain}/{self.dataset_id}")
        return self._meta

    def refresh(self) -> "DatasetClient":
        """Clear cached metadata so the next access re-fetches from the registry."""
        self._meta = None
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
        meta = self._ensure_meta()
        level_order: List[Dict[str, Any]] = meta.get("level_order") or []
        filter_values: Dict[str, list] = meta.get("filter_values") or {}
        return {
            level["column"]: {
                "default": level.get("default_value"),
                "valid": filter_values.get(level["column"], []),
            }
            for level in level_order
            if level.get("type") in ("partition", "filter")
        }

    @property
    def availability(self) -> Dict[str, Any]:
        """Date ranges per entity from manifest.availability."""
        return (self._ensure_meta().get("manifest") or {}).get("availability", {})

    @property
    def description(self) -> Optional[str]:
        """Dataset description."""
        return self._ensure_meta().get("description")

    def _validate_filters(self, filter_dims: Dict[str, Any]) -> None:
        """Validate filter kwargs against registry metadata.

        Raises ValueError with actionable messages when:
        - A filter name is not a known dimension for this dataset.
        - A filter value is not in the set of valid values.
        """
        known = self.filters  # triggers metadata fetch if needed
        if not known:
            return  # no metadata yet — skip validation, let server decide

        for key, val in filter_dims.items():
            # Strip trailing "2" suffix (e.g. sex2 → sex) for system-2 dims
            base_key = key.rstrip("2") if key.endswith("2") and key[:-1] in known else key
            if base_key not in known:
                available = ", ".join(sorted(known))
                raise ValueError(
                    f"Unknown filter '{key}' for {self.domain}/{self.dataset_id}. "
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
                        f"on {self.domain}/{self.dataset_id}. "
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
        self._validate_filters(filter_dims)
        return self._instrument.allotax(
            self.domain, self.dataset_id,
            entity=entity, entity2=entity2, dates=dates, dates2=dates2,
            alpha=alpha, alphas=alphas,
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
        self._validate_filters(filters)
        return self._instrument.rtd(
            self.domain, self.dataset_id,
            entity=entity, dates=dates, dates2=dates2,
            alpha=alpha, alphas=alphas,
            ngram_limit=ngram_limit, wordshift_limit=wordshift_limit,
            **filters,
        )

    def __repr__(self) -> str:
        return f"DatasetClient('{self.domain}/{self.dataset_id}')"


class Storywrangler:
    """Top-level Storywrangler API client.

    Args:
        base_url: API base URL. Defaults to STORYWRANGLER_URL env var or http://localhost:8000.
        api_key:  API key (Bearer token). Defaults to API_KEY env var.
        timeout:  Request timeout in seconds. Defaults to 300 (5 min) to
                  accommodate slow parquet introspection over NFS.
    """

    def __init__(self, base_url: str = None, api_key: str = None, timeout: int = 300) -> None:
        base_url = (base_url or os.getenv("STORYWRANGLER_URL", "http://localhost:8000")).rstrip("/")
        api_key = api_key or os.getenv("API_KEY")
        if not api_key:
            raise ValueError(
                "No API key — set API_KEY env var or pass api_key=. "
                "Use Storywrangler.login(username, password) to retrieve your key."
            )
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })
        if base_url.startswith("https"):
            self._session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._base_url = base_url
        self.registry = RegistryClient(self._session, base_url, timeout)
        self.instrument = InstrumentClient(self._session, base_url, timeout)
        self.users = UsersClient(self._session, base_url, timeout)

    def dataset(self, domain: str, dataset_id: str) -> DatasetClient:
        """Return a dataset-scoped client with filter discovery and instrument methods.

        Example::

            wiki = client.dataset("wikimedia", "ngrams")
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
        base_url = (base_url or os.getenv("STORYWRANGLER_URL", "http://localhost:8000")).rstrip("/")
        verify = not base_url.startswith("https")
        resp = requests.post(
            f"{base_url}/auth/login",
            json={"username": username, "password": password},
            verify=verify,
        )
        resp.raise_for_status()
        api_key = resp.json()["api_key"]
        return cls(base_url=base_url, api_key=api_key)
