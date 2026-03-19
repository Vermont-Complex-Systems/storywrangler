"""
Adapter — Prepare

Validates data against Storywrangler specifications before submission.

What to implement:
  - connect to your storage (ducklake, parquet, duckdb)
  - call EndpointValidator to check schema fits the target endpoint
  - call EntityValidator to check entity IDs in config/entities.yaml

What NOT to do here:
  - entity coverage checks (data vs yaml consistency) → tests/test_coverage.py
  - building the registration payload → adapter/submit.py
"""

import os
import yaml
from pathlib import Path

from storywrangler.validation import EntityValidator, EndpointValidator
from pyprojroot import here
from dotenv import load_dotenv

load_dotenv(override=True)


class MyDatasetValidator:

    def __init__(self):
        self.project_root = here()
        self.dataset_id = os.getenv("DATASET_ID")
        self.data_path = Path(os.getenv("DATA_PATH"))
        self.entity_validator = EntityValidator()
        self.endpoint_validator = EndpointValidator()
        self.entities_path = self.project_root / "config" / "entities.yaml"

    def get_entities(self) -> list[dict]:
        """Load entity mappings from config/entities.yaml."""
        with open(self.entities_path) as f:
            mappings = yaml.safe_load(f)
        return [{"local_id": local_id, **mapping} for local_id, mapping in mappings.items()]

    def validate_entities(self) -> list[dict]:
        """Validate all entity IDs against Storywrangler standards."""
        entities = self.get_entities()
        for e in entities:
            if not self.entity_validator.validate(e["entity_id"]):
                raise ValueError(f"Invalid entity_id for '{e['local_id']}': {e['entity_id']}")
        print(f"Entity validation passed ({len(entities)} entities)")
        return entities

    def validate_schema(self, conn):
        """Validate data schema against the target endpoint spec.

        Replace with your endpoint type and column mapping.
        See EndpointValidator for available endpoint types.
        """
        # Example for types-counts endpoint:
        #
        # schema_result = conn.execute("DESCRIBE my_table").fetchall()
        # columns = {row[0]: {"type": row[1]} for row in schema_result}
        # validation = self.endpoint_validator.validate_types_counts_schema({"columns": columns})
        # if not validation["valid"]:
        #     for error in validation["errors"]:
        #         print(f"  - {error}")
        #     raise ValueError("Schema does not conform to endpoint requirements")
        # print("Schema validation passed")
        raise NotImplementedError("Implement validate_schema for your storage and endpoint type")

    def validate(self):
        """Validate data: entity IDs and schema conformance.

        Entity coverage (data vs entities.yaml) is tested in tests/.
        """
        print(f"Validating {self.dataset_id}\n")

        self.validate_entities()

        # Connect to your storage here, then call validate_schema(conn)
        raise NotImplementedError("Connect to storage and call validate_schema")


def main():
    validator = MyDatasetValidator()

    print("Configuration:")
    print(f"  Dataset ID: {validator.dataset_id}")
    print(f"  Data path:  {validator.data_path}")
    print(f"  Entities:   {validator.entities_path}")
    print()

    validator.validate()


if __name__ == "__main__":
    main()
