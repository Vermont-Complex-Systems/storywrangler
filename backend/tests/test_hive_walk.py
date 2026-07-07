"""
Tests for _walk_levels() — the shared hive-tree walker behind availability,
bucket-config, and filter-value introspection.

Covers:
  - expand: every branch visited, values recorded in context
  - pin: single representative branch followed
  - endpoints: min/max tracking with numeric-aware ordering (month=2 < month=10)
  - fan-out cap
  - _hive_distinct_values: completeness across sibling branches
"""
import os
import sys
from pathlib import Path

# Ensure backend app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.parquet_introspect import _hive_distinct_values, _walk_levels


def make_tree(root, paths):
    for p in paths:
        os.makedirs(os.path.join(root, p), exist_ok=True)


LEVELS = [
    {"column": "year", "type": "time_partition"},
    {"column": "month", "type": "time_partition"},
]


class TestWalkLevels:
    def test_expand_visits_all_branches_with_context(self, tmp_path):
        root = str(tmp_path)
        make_tree(root, ["year=2023/month=2", "year=2023/month=10", "year=2024/month=1"])

        work = _walk_levels(root, LEVELS, lambda lv: "expand")
        contexts = sorted(tuple(sorted(ctx.items())) for _, ctx, _ in work)
        assert contexts == [
            (("month", "1"), ("year", "2024")),
            (("month", "10"), ("year", "2023")),
            (("month", "2"), ("year", "2023")),
        ]
        assert all(bound is None for _, _, bound in work)

    def test_pin_follows_single_branch(self, tmp_path):
        root = str(tmp_path)
        make_tree(root, ["year=2023/month=2", "year=2024/month=1"])

        work = _walk_levels(root, LEVELS, lambda lv: "pin")
        assert len(work) == 1
        # Numeric-aware sort: year=2023 is the first branch
        assert work[0][0].endswith(os.path.join("year=2023", "month=2"))

    def test_endpoints_track_min_max_numerically(self, tmp_path):
        """month=2 must be the min endpoint and month=10 the max — a plain
        lexicographic sort would invert them."""
        root = str(tmp_path)
        make_tree(root, ["year=2023/month=2", "year=2023/month=10"])

        work = _walk_levels(root, LEVELS, lambda lv: "endpoints")
        bounds = {bound: path for path, _, bound in work}
        assert bounds["min"].endswith("month=2")
        assert bounds["max"].endswith("month=10")

    def test_endpoints_stay_directional_across_levels(self, tmp_path):
        root = str(tmp_path)
        make_tree(root, [
            "year=2023/month=3", "year=2023/month=11",
            "year=2025/month=1", "year=2025/month=9",
        ])

        work = _walk_levels(root, LEVELS, lambda lv: "endpoints")
        bounds = {bound: path for path, _, bound in work}
        # min follows first/first; max follows last/last
        assert bounds["min"].endswith(os.path.join("year=2023", "month=3"))
        assert bounds["max"].endswith(os.path.join("year=2025", "month=9"))

    def test_fan_out_cap(self, tmp_path, monkeypatch):
        from app.core import parquet_introspect
        monkeypatch.setattr(parquet_introspect, "_MAX_WORK", 3)

        root = str(tmp_path)
        make_tree(root, [f"year={y}" for y in range(2000, 2010)])

        work = _walk_levels(root, LEVELS[:1], lambda lv: "expand")
        assert len(work) == 3

    def test_non_hive_directories_stop_the_walk(self, tmp_path):
        root = str(tmp_path)
        os.makedirs(os.path.join(root, "not-a-partition"))
        assert _walk_levels(root, LEVELS, lambda lv: "expand") == []


class TestHiveDistinctValues:
    def test_collects_values_across_sibling_branches(self, tmp_path):
        """month values must be unioned across all year directories."""
        root = str(tmp_path)
        make_tree(root, ["year=2023/month=11", "year=2023/month=12", "year=2024/month=1"])

        assert _hive_distinct_values(root, LEVELS, "month") == ["1", "11", "12"]
        assert _hive_distinct_values(root, LEVELS, "year") == ["2023", "2024"]

    def test_unknown_column_returns_empty(self, tmp_path):
        root = str(tmp_path)
        make_tree(root, ["year=2023/month=1"])
        assert _hive_distinct_values(root, LEVELS, "nope") == []
