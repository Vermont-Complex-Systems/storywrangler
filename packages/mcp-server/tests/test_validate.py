"""Tests for validate_submission — schema layer, mirrored guards, lints, disk checks."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from storywrangler_mcp.validate import validate_submission


def base_payload(**overrides):
    payload = {
        "catalog": "vcsi",
        "domain": "babynames",
        "dataset_id": "ngrams",
        "data_location": "/data/babynames/ngrams.parquet",
        "data_format": "parquet",
        "description": "Baby names by year and sex.",
        "endpoint_schema": {"type": "types-counts"},
        "transform": {"filter_dimensions": ["sex"]},
        "ownership": {"owner_group": "vcsi", "contact": "compstorylab@uvm.edu"},
        "lineage": {"repo": "https://github.com/Vermont-Complex-Systems/babynames"},
    }
    payload.update(overrides)
    return payload


def test_minimal_valid_payload():
    report = validate_submission(base_payload(), check_disk=False)
    assert report["valid"], report["errors"]
    assert not report["warnings"]


def test_pydantic_errors_surface():
    payload = base_payload()
    del payload["ownership"]
    report = validate_submission(payload, check_disk=False)
    assert not report["valid"]
    assert any("ownership" in e for e in report["errors"])


def test_types_counts_needs_comparison_axis():
    report = validate_submission(base_payload(transform=None), check_disk=False)
    assert not report["valid"]
    assert any("comparison axis" in e for e in report["errors"])


def test_parquet_hive_counts_as_comparison_axis():
    report = validate_submission(
        base_payload(transform=None, data_format="parquet_hive", data_location="/data/hive"),
        check_disk=False,
    )
    assert not any("comparison axis" in e for e in report["errors"])


def test_time_series_needs_time_dimension():
    report = validate_submission(
        base_payload(
            endpoint_schema={"type": "time-series"},
            transform={"filter_dimensions": ["field"]},
        ),
        check_disk=False,
    )
    assert any("time_dimension" in e for e in report["errors"])


def test_stray_endpoint_schema_keys_warn():
    report = validate_submission(
        base_payload(endpoint_schema={"type": "types-counts", "granularity": "daily"}),
        check_disk=False,
    )
    assert any("granularity" in w and "silently ignored" in w for w in report["warnings"])


def test_stray_transform_keys_warn():
    report = validate_submission(
        base_payload(transform={"filter_dimensions": ["sex"], "granularities": ["daily"]}),
        check_disk=False,
    )
    assert any("granularities" in w for w in report["warnings"])


def test_hash_bucket_dict_rejected():
    report = validate_submission(
        base_payload(
            data_format="parquet_hive",
            transform={"time_dimension": "date", "hash_bucket": {"column": "b", "default_count": 16}},
        ),
        check_disk=False,
    )
    assert any("column name string" in e for e in report["errors"])


def test_bad_column_identifier():
    report = validate_submission(
        base_payload(endpoint_schema={"type": "types-counts", "count_column": "pv count"}),
        check_disk=False,
    )
    assert any("plain identifier" in e for e in report["errors"])


def test_odd_version_warns():
    report = validate_submission(base_payload(version="v1"), check_disk=False)
    assert any("semver" in w for w in report["warnings"])


def test_hive_root_pointing_inside_tree_warns():
    report = validate_submission(
        base_payload(
            data_format="parquet_hive",
            data_location="/data/ngrams/ngram_size=1",
            transform={"time_dimension": "date"},
        ),
        check_disk=False,
    )
    assert any("hive ROOT" in w for w in report["warnings"])


def test_declared_columns_checked_against_supplied_schema():
    report = validate_submission(
        base_payload(
            data_schema={"types": "VARCHAR", "counts": "BIGINT"},
            endpoint_schema={"type": "types-counts", "count_column": "pv_count"},
        ),
        check_disk=False,
    )
    assert any("pv_count" in e for e in report["errors"])


def test_schema_version_noted():
    report = validate_submission(base_payload(schema_version="1.0.0"), check_disk=False)
    assert any("auto-populated" in n for n in report["notes"])


# ── Disk layout checks ─────────────────────────────────────────────────────────

def make_tree(root, paths):
    for p in paths:
        os.makedirs(os.path.join(root, p), exist_ok=True)


def hive_payload(root, **transform):
    return base_payload(
        data_format="parquet_hive",
        data_location=str(root),
        transform={"time_dimension": "date", **transform},
    )


def test_disk_valid_hive_tree(tmp_path):
    make_tree(tmp_path, ["ngram_size=1/granularity=daily/country=US/date=2024-01-01"])
    report = validate_submission(hive_payload(tmp_path))
    assert report["valid"], report["errors"]
    assert any("ngram_size" in n for n in report["notes"])


def test_disk_non_hive_name_rejected(tmp_path):
    make_tree(tmp_path, ["1grams/daily"])
    report = validate_submission(hive_payload(tmp_path))
    assert any("col=val" in e for e in report["errors"])


def test_disk_missing_hash_bucket_level(tmp_path):
    make_tree(tmp_path, ["country=US/date=2024-01-01"])
    report = validate_submission(hive_payload(tmp_path, hash_bucket="ngram_bucket"))
    assert any("hash_bucket" in e for e in report["errors"])


def test_disk_unreachable_path_is_note_not_error():
    report = validate_submission(
        base_payload(
            data_format="parquet_hive",
            data_location="/netfiles/nonexistent/hive",
            transform={"time_dimension": "date"},
        )
    )
    assert report["valid"], report["errors"]
    assert any("not reachable" in n for n in report["notes"])
