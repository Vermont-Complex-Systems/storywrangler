"""
Storywrangler entity and endpoint standards — single source of truth.

Implements patterns and rules from the Storywrangler Specification:
https://github.com/vermont-complex-systems/Storywrangler-Specification

Kept in storywrangler-schemas (no extra dependencies) so the registry
field validators can use it without creating a circular import with the SDK.
"""

import re


class Standards:
    """Compiled patterns and schema rules from the Storywrangler Specification.

    Entity identifier formats (§3.1):
      wikidata:Q30            — Wikidata Q-code
      orcid:0000-0000-0000-0000 — ORCID (format check; checksum in EntityValidator)
      ror:abc123xyz           — ROR
      ipeds:123456            — IPEDS unit ID
      doi:10.1234/...         — DOI
      isbn:9780000000000      — ISBN-13 or ISBN-10
      local:domain:value      — dataset-local fallback

    Endpoint schemas (§3.6):
      types-counts: requires columns 'types' (VARCHAR) and 'counts' (INTEGER)
                    Datasets with non-standard column names declare them via
                    endpoint_schema.type_column / endpoint_schema.count_column.
    """

    # §3.1 — Entity identifier patterns
    WIKIDATA = re.compile(r"^wikidata:Q[0-9]+$")
    ORCID    = re.compile(r"^orcid:[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$")
    ROR      = re.compile(r"^ror:[a-z0-9]{9}$")
    IPEDS    = re.compile(r"^ipeds:[0-9]{6}$")
    DOI      = re.compile(r"^doi:10\.[0-9]{4,}/[^\s]+$")
    ISBN_13  = re.compile(r"^isbn:[0-9]{13}$")
    ISBN_10  = re.compile(r"^isbn:[0-9]{9}[0-9X]$")
    LOCAL    = re.compile(r"^local:[a-z0-9_-]+:[a-z0-9_-]+$")

    ENTITY_PATTERNS = [WIKIDATA, ORCID, ROR, IPEDS, DOI, ISBN_13, ISBN_10, LOCAL]

    # §3.6 — Endpoint schemas
    ENDPOINT_SCHEMAS = {
        "types-counts": {
            "required_columns": {
                "types":  "varchar",
                "counts": "integer",
            },
            "response_format": "json_array",
            "ordering": "counts DESC",
        }
    }

    @classmethod
    def valid_entity_id(cls, v: str) -> bool:
        """True if v matches any supported entity ID format (format check only)."""
        return any(p.match(v) for p in cls.ENTITY_PATTERNS)

    @staticmethod
    def spec_url(section: str = "") -> str:
        base = "https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md"
        return f"{base}#{section}" if section else base
