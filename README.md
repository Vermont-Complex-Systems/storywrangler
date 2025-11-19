# Storywrangler

Text analysis platform for computational social science.

## Repository Structure

This is a monorepo containing:

- **`packages/sdk/`** - Entity validation and standards implementation
- **`packages/text/`** - Text processing and n-gram extraction
- **`packages/api/`** - FastAPI application

## Standards Compliance

This implementation follows the [Storywrangler Specification v0.0.1](https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md).

**Specification Repository:** https://github.com/vermont-complex-systems/Storywrangler-Specification

## Development

### Install dependencies
```bash
uv sync
```

### Run API
```bash
uv run --directory packages/api uvicorn app.main:app --reload
```

### Run tests
```bash
uv run pytest
```

## Architecture

- **[Storywrangler-Specification](https://github.com/vermont-complex-systems/Storywrangler-Specification)** - Entity identifier and taxonomy specifications (separate repo)
- **storywrangler-sdk** - Implements specification validators
- **storywrangler-text** - Text processing
- **API** - FastAPI application serving the ecosystem