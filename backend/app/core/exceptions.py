"""Custom exceptions for the Storywrangler API.

Routers raise these; global handlers in main.py convert them to JSON responses.
This follows FastAPI's recommended pattern: separate exception semantics from
HTTP response formatting.
"""


class DataNotAvailableError(Exception):
    """The dataset is registered but its underlying data files are missing."""

    def __init__(self, dataset: str):
        self.dataset = dataset
        super().__init__(f"Data not available for '{dataset}'")


class QueryError(Exception):
    """A DuckDB query failed for reasons other than missing files."""

    def __init__(self, dataset: str):
        self.dataset = dataset
        super().__init__(f"Query failed for '{dataset}'")


class QueryTimeoutError(Exception):
    """A DuckDB query was interrupted because it exceeded the timeout."""

    def __init__(self, dataset: str):
        self.dataset = dataset
        super().__init__(f"Query timed out for '{dataset}'")
