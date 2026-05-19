import duckdb
from functools import lru_cache


class DuckDBClient:
    def __init__(self):
        self.conn = None

    def connect(self):
        if self.conn is None:
            self.conn = duckdb.connect()
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None


@lru_cache()
def get_duckdb_client() -> DuckDBClient:
    return DuckDBClient()
