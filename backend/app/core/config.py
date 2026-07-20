from typing import List

from pydantic import computed_field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Match the variable names already in backend/.env
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "storywrangler"
    postgres_user: str = "postgres"
    postgres_password: str = "changethis"

    # mongoDB URI
    mongodb_uri: str | None = None

    # CORS — override via ALLOWED_ORIGINS env var (comma-separated) in production
    allowed_origins: List[str] = [
        "http://localhost:5173",
        "http://localhost:4173",
        "https://storywrangler.uvm.edu",
    ]

    # DuckDB spill-to-disk location — override via DUCKDB_TEMP_DIRECTORY env var
    duckdb_temp_directory: str = "/netfiles/compethicslab/duckdb_temp"

    # Admin user seeded on startup
    admin_username: str = "admin"
    admin_email: str = "admin@storywrangler.org"
    admin_password: str = "changethis"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
