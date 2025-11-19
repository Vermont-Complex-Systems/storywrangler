from fastapi import FastAPI

app = FastAPI(
    title="Storywrangler API",
    description="API for Storywrangler text analysis platform",
    version="0.0.1"
)

@app.get("/")
async def root():
    return {
        "message": "Storywrangler API",
        "version": "0.0.1",
        "specification": {
            "version": "0.0.1",
            "url": "https://github.com/vermont-complex-systems/Storywrangler-Specification"
        }
    }

@app.get("/specification")
async def get_specification():
    """Return information about supported entity standards"""
    return {
        "version": "0.0.1",
        "spec_url": "https://github.com/vermont-complex-systems/Storywrangler-Specification/blob/main/versions/0.0.1.md",
        "repository": "https://github.com/vermont-complex-systems/Storywrangler-Specification",
        "supported_entities": {
            "identifiers": ["wikidata", "orcid", "ror", "ipeds", "doi", "isbn"],
            "taxonomies": ["wikidata", "arxiv", "mag"]
        }
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}