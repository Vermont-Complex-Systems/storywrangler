"""
Adapter — Submit

Builds the dataset registration payload and submits it to the Storywrangler API.

What to implement:
  - get_entities(): load from config/entities.yaml
  - build the dataset_metadata dict
  - call register(dataset_metadata)

Availability (date ranges) is auto-computed by the server at registration time.
The API validates the registration payload structure.
prepare.py validated the data itself.
"""

import os
import yaml

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


def main():
    dataset_id = os.getenv("DATASET_ID")
    domain = os.getenv("DOMAIN")
    data_location = os.getenv("DATA_PATH")

    entities = get_entities()

    dataset_metadata = {
        "catalog": "vcsi",
        "dataset_id": dataset_id,
        "domain": domain,
        "data_location": data_location,
        "data_format": "parquet",           # parquet | parquet_hive
        "description": "...",
        "entity_mapping": {
            "local_id_column": "geo",       # column in your data holding the local entity ID
        },
        "entities": entities,
        "endpoint_schema": {
            "type": "types-counts",         # endpoint type this dataset supports
        },
        "transform": {
            "time_dimension": "year",       # time column in your data (e.g. "year", "date")
            # "filter_dimensions": ["sex"], # optional: non-hive columns to expose as query filters
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
