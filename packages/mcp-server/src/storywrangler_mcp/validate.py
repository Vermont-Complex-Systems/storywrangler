"""Dry-run validation of a DatasetCreate payload — the svelte-autofixer analog.

Three layers, no server round-trip:

1. Schema: the payload is validated against the real ``storywrangler_schemas``
   Pydantic models — exactly the contract the backend enforces at POST.
2. Guards: payload-level mirrors of the backend registration guards
   (backend/app/routers/registry.py: _validate_column_identifiers,
   _validate_types_counts, _validate_time_series). Checks that need the
   server's data introspection (derived data_schema, level_order) run only
   when the payload supplies the equivalent field.
3. Lints: convention checks for mistakes that would register "successfully"
   but not mean what the submitter intended (Pydantic silently drops unknown
   keys, so a stray ``granularity`` in endpoint_schema vanishes without error).

When ``data_location`` is reachable from this machine (submitters often run on
the same cluster as the data), the hive layout is checked directly; otherwise
layout checks are skipped with a note — the server introspects at registration.

Report shape: ``{"valid": bool, "errors": [...], "warnings": [...], "notes": [...]}``
- errors:   registration would fail (or a declared column cannot work)
- warnings: would register, but almost certainly not what you meant
- notes:    informational (skipped checks, auto-derived fields)
"""
from __future__ import annotations

import os
import re
from typing import Any

from pydantic import ValidationError
from storywrangler_schemas.registry import DatasetCreate

# Mirrors backend/app/routers/registry.py::_IDENT_RE / _ORDER_RE
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ORDER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*( +(ASC|DESC))?$", re.IGNORECASE)
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

_ENDPOINT_SCHEMA_KEYS = {"type", "type_column", "count_column"}
_TRANSFORM_KEYS = {
    "time_dimension",
    "filter_dimensions",
    "time_partitions",
    "hash_bucket",
    "hash_algorithm",
    "hash_seed",
}


def format_report(report: dict[str, Any]) -> str:
    """Render a validation report as agent/CI-friendly text."""
    lines: list[str] = []
    if report["valid"]:
        lines.append("VALID — no blocking errors; registration should be accepted.")
    else:
        lines.append("INVALID — fix the errors below before registering.")
    for level, items in (("Errors", report["errors"]), ("Warnings", report["warnings"]), ("Notes", report["notes"])):
        if items:
            lines.append(f"\n{level}:")
            lines.extend(f"- {item}" for item in items)
    if report["valid"] and not report["warnings"]:
        lines.append(
            "\nNext: register via the SDK, then GET the dataset back and verify "
            "level_order and manifest.availability were derived as expected."
        )
    return "\n".join(lines)


def validate_submission(payload: dict[str, Any], check_disk: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    _check_schema(payload, errors)
    _check_stray_keys(payload, warnings)
    _check_column_identifiers(payload, errors)
    _check_hash_bucket_form(payload, errors)
    _check_version(payload, warnings)
    _check_auto_derived_fields(payload, notes)
    _check_endpoint_type_requirements(payload, errors)
    _check_declared_columns_against_schema(payload, errors)
    _check_data_location_shape(payload, errors, warnings)
    if check_disk:
        _check_disk_layout(payload, errors, warnings, notes)

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "notes": notes,
    }


# ── Layer 1: the real registration schema ─────────────────────────────────────

def _check_schema(payload: dict, errors: list[str]) -> None:
    try:
        DatasetCreate.model_validate(payload)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "payload"
            errors.append(f"schema: {loc} — {err['msg']}")


# ── Layer 2: mirrored backend guards ──────────────────────────────────────────

def _check_column_identifiers(payload: dict, errors: list[str]) -> None:
    """Mirror of _validate_column_identifiers — plain SQL identifiers only."""
    declared: dict[str, Any] = {}
    ep = payload.get("endpoint_schema") or {}
    if isinstance(ep, dict):
        declared["endpoint_schema.type_column"] = ep.get("type_column")
        cc = ep.get("count_column")
        if isinstance(cc, list):
            for col in cc:
                declared[f"endpoint_schema.count_column[{col!r}]"] = col
        else:
            declared["endpoint_schema.count_column"] = cc
        # rank/freq (term-series SELECT) and doc/score (type-documents SELECT).
        for field in ("rank_column", "freq_column"):
            val = ep.get(field)
            for col in (val if isinstance(val, list) else [val] if val else []):
                declared[f"endpoint_schema.{field}[{col!r}]"] = col
        for field in ("doc_column", "score_column"):
            if ep.get(field):
                declared[f"endpoint_schema.{field}"] = ep[field]
    tr = payload.get("transform") or {}
    if isinstance(tr, dict):
        declared["transform.time_dimension"] = tr.get("time_dimension")
        for fd in tr.get("filter_dimensions") or []:
            declared[f"transform.filter_dimensions[{fd!r}]"] = fd
        for tp in tr.get("time_partitions") or []:
            declared[f"transform.time_partitions[{tp!r}]"] = tp
        if isinstance(tr.get("hash_bucket"), str):
            declared["transform.hash_bucket"] = tr["hash_bucket"]
    em = payload.get("entity_mapping") or {}
    if isinstance(em, dict):
        declared["entity_mapping.local_id_column"] = em.get("local_id_column")
    for col in payload.get("data_schema") or {}:
        declared[f"data_schema[{col!r}]"] = col

    for where, name in sorted(declared.items()):
        if name is not None and not _IDENT_RE.match(str(name)):
            errors.append(
                f"guard: {where} = {name!r} is not a plain identifier "
                "(letters, digits, underscore; not starting with a digit) — the server rejects this with 422."
            )

    # order_column reaches ORDER BY verbatim and may carry a sort direction.
    oc = ep.get("order_column") if isinstance(ep, dict) else None
    if oc is not None and not _ORDER_RE.match(str(oc)):
        errors.append(
            f"guard: endpoint_schema.order_column = {oc!r} must be a column name "
            "optionally followed by ASC or DESC — the server rejects this with 422."
        )


def _check_endpoint_type_requirements(payload: dict, errors: list[str]) -> None:
    """Mirror of _validate_types_counts / _validate_time_series (payload-level parts)."""
    ep = payload.get("endpoint_schema") or {}
    if not isinstance(ep, dict) or not ep.get("type"):
        return
    ep_type = ep["type"]
    tr = payload.get("transform") or {}
    tr = tr if isinstance(tr, dict) else {}
    has_entity = bool(payload.get("entity_mapping"))
    has_time = bool(tr.get("time_dimension"))
    has_filter = bool(tr.get("filter_dimensions"))
    # Client-side proxy for the server's derived level_order: parquet_hive
    # datasets get their hive levels auto-discovered.
    has_hive = payload.get("data_format") == "parquet_hive"

    if ep_type == "types-counts":
        if not any([has_entity, has_time, has_filter, has_hive]):
            errors.append(
                "guard: types-counts requires at least one comparison axis "
                "(entity_mapping, transform.time_dimension, transform.filter_dimensions, "
                "or parquet_hive auto-discovered levels) — the server rejects this with 422."
            )
    elif ep_type == "time-series":
        if not has_time:
            errors.append(
                "guard: time-series requires transform.time_dimension — the server rejects this with 422."
            )
        if not has_filter and not has_hive:
            errors.append(
                "guard: time-series requires at least one groupable dimension "
                "(transform.filter_dimensions or parquet_hive levels) — the server rejects this with 422."
            )


def _check_declared_columns_against_schema(payload: dict, errors: list[str]) -> None:
    """When the payload supplies data_schema, verify declared columns exist in it."""
    data_schema = payload.get("data_schema")
    if not isinstance(data_schema, dict) or not data_schema:
        return
    ep = payload.get("endpoint_schema") or {}
    ep = ep if isinstance(ep, dict) else {}
    tr = payload.get("transform") or {}
    tr = tr if isinstance(tr, dict) else {}

    def _count_cols(default: str) -> list[str]:
        # count_column may be a list (selectable measure menu, first = default);
        # every entry must exist since any can reach the query via ?weight=.
        cc = ep.get("count_column") or default
        return cc if isinstance(cc, list) else [cc]

    expected: list[str] = []
    if ep.get("type") == "types-counts":
        expected += [ep.get("type_column") or "types", *_count_cols("counts")]
        for field in ("rank_column", "freq_column"):
            val = ep.get(field)
            expected += (val if isinstance(val, list) else [val] if val else [])
    elif ep.get("type") == "time-series":
        expected += _count_cols("count")
    if tr.get("time_dimension"):
        expected.append(tr["time_dimension"])
    expected += tr.get("filter_dimensions") or []

    missing = [c for c in expected if c not in data_schema]
    if missing:
        errors.append(
            f"guard: column(s) {missing} not found in data_schema {sorted(data_schema)} — "
            "verify type_column/count_column/time_dimension/filter_dimensions match actual column names."
        )


# ── Layer 3: convention lints ─────────────────────────────────────────────────

def _check_stray_keys(payload: dict, warnings: list[str]) -> None:
    """Pydantic silently drops unknown keys — the classic conflation mistake vanishes."""
    ep = payload.get("endpoint_schema")
    if isinstance(ep, dict):
        stray = sorted(set(ep) - _ENDPOINT_SCHEMA_KEYS)
        if stray:
            warnings.append(
                f"lint: endpoint_schema keys {stray} are silently ignored by the server. "
                "endpoint_schema declares output shape only (type, type_column, count_column); "
                "query axes belong in transform, and hive levels are auto-discovered."
            )
    tr = payload.get("transform")
    if isinstance(tr, dict):
        stray = sorted(set(tr) - _TRANSFORM_KEYS)
        if stray:
            warnings.append(
                f"lint: transform keys {stray} are silently ignored by the server. "
                f"Supported: {sorted(_TRANSFORM_KEYS)}. Hive partition levels are "
                "auto-discovered — do not enumerate them."
            )


def _check_hash_bucket_form(payload: dict, errors: list[str]) -> None:
    tr = payload.get("transform")
    if isinstance(tr, dict) and isinstance(tr.get("hash_bucket"), dict):
        errors.append(
            "lint: transform.hash_bucket must be submitted as the column name string "
            "(e.g. 'ngram_bucket'). The {column, default_count, overrides} dict is the "
            "STORED form — the server derives bucket counts from the directory tree."
        )


def _check_version(payload: dict, warnings: list[str]) -> None:
    version = payload.get("version", "latest")
    if version != "latest" and not _SEMVER_RE.match(str(version)):
        warnings.append(
            f"lint: version {version!r} is neither 'latest' nor semver (X.Y.Z). "
            "Use 'latest' for the mutable dev slot; semver strings create immutable snapshots."
        )


def _check_auto_derived_fields(payload: dict, notes: list[str]) -> None:
    if "schema_version" in payload:
        notes.append(
            "note: schema_version is auto-populated from the installed storywrangler-schemas — remove it."
        )
    manifest = payload.get("manifest")
    if isinstance(manifest, dict) and manifest.get("availability"):
        notes.append(
            "note: manifest.availability is auto-derived at registration when "
            "transform.time_dimension is set — no need to compute it client-side."
        )
    if payload.get("entities") and not payload.get("entity_mapping"):
        notes.append(
            "note: entities rows were provided without entity_mapping — the server needs "
            "entity_mapping.local_id_column to know which column they map."
        )


def _check_data_location_shape(payload: dict, errors: list[str], warnings: list[str]) -> None:
    loc = payload.get("data_location")
    fmt = payload.get("data_format")
    if fmt != "parquet_hive":
        return
    if isinstance(loc, list):
        errors.append(
            "lint: data_location file lists are only supported for data_format='parquet'; "
            "parquet_hive takes the root directory of the hive tree."
        )
        return
    if isinstance(loc, str) and "=" in os.path.basename(loc.rstrip("/")):
        warnings.append(
            f"lint: data_location {loc!r} ends in a col=val segment — it should point at the "
            "hive ROOT, the directory directly above the first col=val level."
        )


# ── Optional: direct layout checks when the data is reachable ─────────────────

def _check_disk_layout(payload: dict, errors: list[str], warnings: list[str], notes: list[str]) -> None:
    loc = payload.get("data_location")
    if payload.get("data_format") == "mongodb":
        notes.append(
            "note: mongodb is a pass-through format — no on-disk layout to check. "
            "The server introspects the collection live at registration (requires "
            "MONGODB_URI configured server-side); no level_order or hash buckets are "
            "derived, and queries are equality filters + time range only."
        )
        return
    if not isinstance(loc, str):
        return
    if not os.path.exists(loc):
        notes.append(
            f"note: data_location {loc!r} is not reachable from this machine — layout checks "
            "skipped (the server introspects it at registration)."
        )
        return

    fmt = payload.get("data_format")
    if fmt == "parquet":
        if os.path.isfile(loc):
            if not loc.endswith(".parquet"):
                warnings.append(f"disk: {loc!r} exists but is not a .parquet file.")
        elif not any(f.endswith(".parquet") for f in os.listdir(loc)):
            warnings.append(f"disk: directory {loc!r} contains no .parquet files at the top level.")
        return

    if fmt != "parquet_hive":
        return

    # Walk one branch of the hive tree, collecting level columns — the same
    # single-branch discovery the server's introspection performs.
    levels: list[str] = []
    current = loc
    while True:
        subdirs = sorted(
            d for d in os.listdir(current) if os.path.isdir(os.path.join(current, d))
        )
        if not subdirs:
            break
        first = subdirs[0]
        if "=" not in first:
            errors.append(
                f"disk: directory {first!r} under {current!r} does not follow the col=val "
                "convention — every hive level must be named col=val (e.g. ngram_size=1)."
            )
            return
        levels.append(first.split("=", 1)[0])
        current = os.path.join(current, first)

    if not levels:
        errors.append(
            f"disk: no col=val subdirectories found under {loc!r} — parquet_hive requires a "
            "hive-partitioned tree, or use data_format='parquet' for flat layouts."
        )
        return

    notes.append(f"note: discovered hive levels (first branch): {levels}.")

    tr = payload.get("transform") or {}
    tr = tr if isinstance(tr, dict) else {}
    em = payload.get("entity_mapping") or {}
    em = em if isinstance(em, dict) else {}

    time_dim = tr.get("time_dimension")
    if time_dim and time_dim not in levels and "time_partitions" not in tr:
        warnings.append(
            f"disk: transform.time_dimension {time_dim!r} is not a hive level {levels} — "
            "fine only if it is a column inside the parquet files."
        )
    hash_bucket = tr.get("hash_bucket")
    if isinstance(hash_bucket, str) and hash_bucket not in levels:
        errors.append(
            f"disk: transform.hash_bucket {hash_bucket!r} is not among the hive levels {levels} — "
            "the server rejects this with 422."
        )
    local_id = em.get("local_id_column")
    if local_id and local_id not in levels:
        warnings.append(
            f"disk: entity_mapping.local_id_column {local_id!r} is not a hive level {levels} — "
            "for parquet_hive the entity column is normally a partition directory."
        )
