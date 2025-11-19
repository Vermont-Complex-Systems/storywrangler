# packages/api/app/main.py

from fastapi import FastAPI
from app.routers import datasets, women_in_mathematics

app = FastAPI(
    title="Storywrangler API",
    version="0.0.1",
    description="Text analysis platform API"
)

# Register routers
app.include_router(datasets.router)
app.include_router(women_in_mathematics.router)


@app.get("/")
async def root():
    return {
        "message": "Storywrangler API",
        "version": "0.0.1",
        "specification": "https://github.com/vermont-complex-systems/Storywrangler-Specification"
    }