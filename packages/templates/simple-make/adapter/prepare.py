"""
prepare.py — no longer needed.

Entity ID format validation now runs automatically when you POST to /register:
the EntityRow.entity_id field validator (storywrangler_schemas.registry) checks
every entity_id against the supported namespaces (wikidata, orcid, ror, ipeds,
doi, isbn, local) and returns a 422 with a clear error if the format is wrong.

Column name validation (types / counts) also runs at registration time.

To register, run submit.py directly:
  uv run python adapter/submit.py
"""
