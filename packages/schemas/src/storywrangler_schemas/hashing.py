"""Canonical hash-bucket assignment for content-sharded datasets.

Both the backend (query routing) and pipelines (data partitioning) MUST
use this function to ensure bucket assignments are consistent.
"""

import mmh3

HASH_ALGORITHM = "murmur3_32"
HASH_SEED = 0


def assign_bucket(term: str, num_buckets: int) -> int:
    """Assign a term to a hash bucket.

    Uses murmur3_32 with seed 0 and clears the sign bit so bucket IDs
    are always non-negative.  This matches DuckDB's built-in murmur3_32()
    default.

    Pipeline code producing hash-bucketed parquet_hive datasets MUST use
    this function (or an exact reimplementation) to partition files into
    ``{hash_bucket_column}={bucket}/`` directories.
    """
    return (mmh3.hash(term, seed=HASH_SEED) & 0x7FFFFFFF) % num_buckets
