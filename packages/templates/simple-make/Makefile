.PHONY: extract transform prepare submit test

# ── Extract ───────────────────────────────────────────────────
# Download or scrape raw source data.
extract:
	uv run python extract/src/scrape.py

# ── Transform ─────────────────────────────────────────────────
# Process raw data into storage format (ducklake, parquet, etc.).
transform:
	uv run python transform/src/process.py

# ── Adapter: prepare ──────────────────────────────────────────
# Validate data against Storywrangler specifications.
prepare:
	uv run python adapter/prepare.py

# ── Adapter: submit ───────────────────────────────────────────
# Register dataset with the Storywrangler API.
submit:
	uv run python adapter/submit.py

# ── Tests ─────────────────────────────────────────────────────
# Run data coverage tests (entity mappings, null checks, etc.).
test:
	uv run pytest tests/
