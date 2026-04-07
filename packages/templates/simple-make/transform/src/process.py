"""
Transform — process raw data into storage format.

Replace this with your actual transformation logic.
Common patterns:
  - Load raw files from extract/input/, write to parquet or parquet_hive
  - Normalize, deduplicate, compute counts/ranks
  - Partition by entity column and time dimension

Output should be the storage format your adapter/prepare.py expects.
"""


def main():
    raise NotImplementedError("Implement your transformation logic here")


if __name__ == "__main__":
    main()
