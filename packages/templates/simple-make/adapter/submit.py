"""
Adapter — Submit

Builds the dataset registration payload and submits it to the Storywrangler API.

What to implement:
  - get_entities(): load from config/entities.yaml
  - get_availability(): compute coverage metadata (date ranges, year ranges, etc.)
  - build the dataset_metadata dict
  - call register(dataset_metadata)

The API validates the registration payload structure.
prepare.py validated the data itself.
"""

import os
import yaml
from pathlib import Path

from pyprojroot import here
from storywrangler import Storywrangler
from dotenv import load_dotenv

load_dotenv(override=True)


def get_entities() -> list[dict]:
    """Load entity mappings from config/entities.yaml."""
    entities_path = here() / "config" / "entities.yaml"
    with open(entities_path) as f:
        mappings = yaml.safe_load(f)
    return [{"local_id": local_id, **mapping} for local_id, mapping in mappings.items()]


def get_availability(conn) -> dict:
    """Compute data coverage metadata (e.g. date ranges per entity).

    Example for a yearly dataset keyed by geo:

        rows = conn.execute(
            "SELECT geo, MIN(year), MAX(year) FROM my_table GROUP BY geo"
        ).fetchall()
        return {"yearly": {"available": {geo: {"min": mn, "max": mx} for geo, mn, mx in rows}}}
    """
    raise NotImplementedError("Implement get_availability for your dataset")


def main():
    dataset_id = os.getenv("DATASET_ID")
    domain = os.getenv("DOMAIN")
    data_location = os.getenv("DATA_PATH")

    entities = get_entities()

    # conn = ...  connect to your storage
    # availability = get_availability(conn)

    dataset_metadata = {
        "catalog": "vcsi",
        "dataset_id": dataset_id,
        "domain": domain,
        "data_location": data_location,
        "data_format": "parquet",           # parquet | parquet_hive
        "description": "...",
        "manifest": {
            # "availability": availability,
        },
        "entity_mapping": {
            "local_id_column": "geo",       # column in your data holding the local entity ID
        },
        "entities": entities,
        "endpoint_schema": {
            "type": "types-counts",         # endpoint type this dataset supports
        },
        "transform": {
            "time_dimension": "year",       # time column in your data (e.g. "year", "date")
            # "filter_dimensions": ["sex"], # hive partition columns to expose as query filters
        },
        "ownership": {
            "owner_group": "vcsi",
            "contact": "your@email.edu",
            "storage_risk": "institutional",
        },
        "lineage": {
            "sources": {
                # "geo": {"US": "https://..."}
            },
            "derived_from": [],
        },
    }

    client = Storywrangler()  # reads API_KEY (and optionally API_URL) from .env
    success = client.registry.register(dataset_metadata)
    if success:
        print(f"\n{dataset_id} registered successfully")
    else:
        print(f"\nRegistration failed")


if __name__ == "__main__":
    main()
