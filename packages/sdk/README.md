# Storywrangler SDK

Entity and taxonomy validation for Storywrangler.

## Standards

This package implements validation rules defined in the [Storywrangler Specification](https://github.com/vermont-complex-systems/Storywrangler-Specification).

**Current version:** v0.0.1

See [versions/0.0.1.md](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md) for specification details.

## Installation
```bash
pip install storywrangler-sdk
```

## Usage
```python
from storywrangler.validation import EntityValidator

validator = EntityValidator()

# Validate Wikidata Q-code (Spec: Section 3.1.1)
validator.validate_wikidata("wikidata:Q937")  # True

# Validate ORCID (Spec: Section 3.1.2)
validator.validate_orcid("orcid:0000-0002-1825-0097")  # True

# Validate any entity ID
validator.validate("ror:05qghxh33")  # True
```

## Standards Compliance

This SDK implements [Storywrangler Specification v0.0.1](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md).

All validators follow the format requirements and validation algorithms defined in the specification.