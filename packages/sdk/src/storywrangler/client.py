"""
Storywrangler client — Label Studio-style API wrapper.

Usage:
    # Option 1: provide api_key directly (or via API_KEY env var)
    from storywrangler import Storywrangler
    client = Storywrangler(base_url="http://localhost:8000", api_key="<your-key>")

    # Option 2: login with username/password to get a client
    client = Storywrangler.login("admin", "changethis", base_url="http://localhost:8000")

    # Verify connection
    me = client.users.whoami()
    print(me["username"], me["role"])

    # Register a dataset
    client.registry.register(dataset_create_instance)
"""

from __future__ import annotations

import os
from typing import Any, Dict

import requests

from .registry.models import DatasetCreate


class _SubClient:
    """Base class for sub-resource clients — shares the parent session."""

    def __init__(self, session: requests.Session, base_url: str) -> None:
        self._session = session
        self._base_url = base_url

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _get(self, path: str, **kwargs) -> requests.Response:
        return self._session.get(self._url(path), **kwargs)

    def _post(self, path: str, **kwargs) -> requests.Response:
        return self._session.post(self._url(path), **kwargs)

    def _put(self, path: str, **kwargs) -> requests.Response:
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


class UsersClient(_SubClient):
    """Interact with /auth endpoints."""

    def whoami(self) -> Dict[str, Any]:
        """Return the current user's profile."""
        resp = self._get("/auth/me")
        resp.raise_for_status()
        return resp.json()


class Storywrangler:
    """Top-level Storywrangler API client.

    Args:
        base_url: API base URL. Defaults to STORYWRANGLER_URL env var or http://localhost:8000.
        api_key:  API key (Bearer token). Defaults to API_KEY env var.
    """

    def __init__(self, base_url: str = None, api_key: str = None) -> None:
        base_url = (base_url or os.getenv("STORYWRANGLER_URL", "http://localhost:8000")).rstrip("/")
        api_key = api_key or os.getenv("API_KEY")
        if not api_key:
            raise ValueError(
                "No API key — set API_KEY env var or pass api_key=. "
                "Use Storywrangler.login(username, password) to retrieve your key."
            )
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })
        self.registry = RegistryClient(self._session, base_url)
        self.users = UsersClient(self._session, base_url)

    @classmethod
    def login(cls, username: str, password: str, base_url: str = None) -> "Storywrangler":
        """Authenticate with username/password and return a configured client.

        Example:
            client = Storywrangler.login("admin", "changethis")
            print(client.users.whoami())
        """
        base_url = (base_url or os.getenv("STORYWRANGLER_URL", "http://localhost:8000")).rstrip("/")
        resp = requests.post(
            f"{base_url}/auth/login",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        api_key = resp.json()["api_key"]
        return cls(base_url=base_url, api_key=api_key)
