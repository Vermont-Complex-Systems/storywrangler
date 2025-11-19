from fastapi import FastAPI

app = FastAPI(
    title="Storywrangler API",
    description="API for Storywrangler text analysis platform",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"message": "Storywrangler API", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/api/datasets")
async def get_datasets():
    return {"datasets": []}