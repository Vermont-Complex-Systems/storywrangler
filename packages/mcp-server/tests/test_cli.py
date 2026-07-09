"""Tests for the CLI mode — validate-submission exit codes and dispatch."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from storywrangler_mcp.cli import main


def payload(**overrides):
    base = {
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
    base.update(overrides)
    return base


def run_validate(tmp_path, data, *extra):
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(data))
    with pytest.raises(SystemExit) as exc:
        main(["validate-submission", str(path), *extra])
    return exc.value.code


def test_valid_payload_exits_zero(tmp_path, capsys):
    code = run_validate(tmp_path, payload(), "--no-disk")
    assert code == 0
    assert "VALID" in capsys.readouterr().out


def test_invalid_payload_exits_one(tmp_path, capsys):
    bad = payload(transform=None)  # no comparison axis
    code = run_validate(tmp_path, bad, "--no-disk")
    assert code == 1
    assert "comparison axis" in capsys.readouterr().out


def test_malformed_json_exits_two(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text("{not json")
    with pytest.raises(SystemExit) as exc:
        main(["validate-submission", str(path)])
    assert exc.value.code == 2


def test_stdin_payload(tmp_path, capsys, monkeypatch):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload())))
    with pytest.raises(SystemExit) as exc:
        main(["validate-submission", "-", "--no-disk"])
    assert exc.value.code == 0
    assert "VALID" in capsys.readouterr().out
