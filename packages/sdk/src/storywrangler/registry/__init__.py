"""
Storywrangler registry client — submit dataset registrations to the platform API.
"""

import os
import requests

from .models import DatasetCreate, EndpointSchemaConfig, EntityMappingConfig

__all__ = ["register", "DatasetCreate", "EndpointSchemaConfig", "EntityMappingConfig"]


def register(
    payload: "DatasetCreate | dict",
    api_url: str = None,
    token: str = None,
) -> bool:
    """Register or update a dataset in the Storywrangler platform registry.

    Validates the payload against DatasetCreate before submitting. Raises
    ValidationError immediately if required fields are missing or have wrong
    types — rather than waiting for a 422 from the API.

    Reads API_URL and API_TOKEN (or JWT_TOKEN as fallback) from environment
    if not provided as arguments. Registration is an upsert: safe to re-run
    after data or metadata changes.

    Args:
        payload: DatasetCreate instance or equivalent dict. See models.py.
        api_url: Base URL of the platform API. Defaults to API_URL env var or http://localhost:8000.
        token: Auth token (API key or JWT). Defaults to API_TOKEN env var, then JWT_TOKEN.

    Returns:
        True on success, False on failure.

    Raises:
        pydantic.ValidationError: If the payload fails schema validation.
        ValueError: If no token is found in arguments or environment.
        requests.exceptions.ConnectionError: If the API is unreachable.
    """
    api_url = api_url or os.getenv("API_URL", "http://localhost:8000")
    token = token or os.getenv("API_TOKEN") or os.getenv("JWT_TOKEN")

    if not token:
        raise ValueError("No auth token found — set API_TOKEN in .env or pass token=")

    # Validate and normalise — raises pydantic.ValidationError on bad input
    if not isinstance(payload, DatasetCreate):
        payload = DatasetCreate.model_validate(payload)

    dataset_id = payload.dataset_id

    try:
        response = requests.post(
            f"{api_url}/admin/registry/register",
            json=payload.model_dump(mode="json", exclude_none=True),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        if response.status_code in [200, 201]:
            print(f"  {dataset_id} registered successfully!")
            return True
        else:
            print(f"  {dataset_id} failed: {response.status_code}")
            print(f"    {response.text[:500]}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"  Could not connect to {api_url}")
        return False
    except Exception as e:
        print(f"  Unexpected error: {type(e).__name__}: {e}")
        return False
