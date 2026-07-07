"""Scalar coercion shared by the backend query layer and the SDK.

Query parameters arrive as strings, but registry filter_values store typed
values (int 1, float 0.17). Both sides must coerce identically before
membership checks — keeping this in one place prevents drift.
"""


def coerce_scalar(value):
    """Coerce a string to int, then float; return the original on failure.

    Non-strings pass through unchanged.
    """
    if not isinstance(value, str):
        return value
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value
