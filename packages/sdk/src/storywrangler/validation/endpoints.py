"""
EndpointValidator — deprecated.

Column name validation has moved server-side: the POST /register endpoint
checks that declared type_column / count_column exist in the parquet schema
at registration time and returns a 422 with a clear error message.

This module is kept as a stub to avoid breaking existing imports.
"""


class EndpointValidator:
    """Deprecated. Column validation now runs automatically at POST /register."""

    def __init__(self):
        import warnings
        warnings.warn(
            "EndpointValidator is deprecated and does nothing. "
            "Column validation runs automatically at POST /register.",
            DeprecationWarning,
            stacklevel=2,
        )

    def validate_types_counts_schema(self, _schema):
        return {"valid": True, "errors": [], "warnings": ["EndpointValidator is deprecated"], "column_mapping": {}}

    def validate_endpoint_schema(self, _endpoint_name, _schema):
        return {"valid": True, "errors": [], "warnings": ["EndpointValidator is deprecated"], "column_mapping": {}}
