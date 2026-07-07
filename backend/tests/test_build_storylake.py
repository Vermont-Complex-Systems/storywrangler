"""
Tests for build_storylake._resolve_views — view FROM-expressions per dataset.

The script itself needs PostgreSQL + registered datasets; the path-resolution
logic is pure and tested here.
"""
import importlib.util
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# The script reads POSTGRES_* at import time; provide fallbacks so the
# import works without a configured backend/.env.
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

_spec = importlib.util.spec_from_file_location(
    "build_storylake", BACKEND_DIR / "scripts" / "build_storylake.py")
build_storylake = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_storylake)

_resolve_views = build_storylake._resolve_views


LEVEL_ORDER = [
    {"column": "ngram_size", "type": "partition", "default_value": 1},
    {"column": "country", "type": "entity", "default_value": "Afghanistan"},
    {"column": "ngram_bucket", "type": "hash_bucket", "default_value": 0},
    {"column": "date", "type": "time", "default_value": "2020-01-01"},
]


class TestResolveViews:
    def test_parquet_single_file(self):
        assert _resolve_views("names", "parquet", "/data/names.parquet", None) == [
            ("names", "read_parquet('/data/names.parquet')"),
        ]

    def test_parquet_file_list(self):
        assert _resolve_views("oaa", "parquet", ["/a.parquet", "/b.parquet"], None) == [
            ("oaa", "read_parquet(['/a.parquet', '/b.parquet'])"),
        ]

    def test_parquet_hive_with_level_order_uses_fixed_depth_glob(self):
        views = _resolve_views("wiki", "parquet_hive", "/data/wikigrams", LEVEL_ORDER)
        assert views == [
            ("wiki", "read_parquet('/data/wikigrams/*/*/*/*/*.parquet', hive_partitioning=true)"),
        ]

    def test_parquet_hive_without_level_order_falls_back_to_recursive_glob(self):
        views = _resolve_views("wiki", "parquet_hive", "/data/wikigrams", None)
        assert views == [
            ("wiki", "read_parquet('/data/wikigrams/**/*.parquet', hive_partitioning=true)"),
        ]

    def test_unknown_format_yields_nothing(self):
        assert _resolve_views("x", "duckdb", "/data/x.duckdb", None) == []
