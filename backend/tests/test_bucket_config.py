"""k-agreement tests for hash-bucket derivation and resolution.

The invariant that makes hash routing correct: for every leaf, the bucket
count the query layer resolves at request time must equal the number of
bucket directories the pipeline actually wrote (which _derive_bucket_config
counted at registration). A mismatch changes the modulus and silently routes
terms to the wrong shard.

Covers both layout shapes:
  1. entity × partition   (wikimedia sparklines: ngram_size / country / bucket)
  2. partition-only        (reddit sparklines: n / lang / ngram_bucket)
     — the shape that exposed the original bug: override keys dropped the
     second partition dim, and resolution short-circuited to default_count
     whenever there was no entity.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.duckdb_query import bucket_override_key, resolve_bucket_count
from app.core.parquet_introspect import _derive_bucket_config


def _mktree(root: Path, leaves: dict) -> None:
    """leaves: {"ngram_size=1/country=A": n_buckets, ...} (bucket col from key)."""
    for leaf, (bucket_col, k) in leaves.items():
        for b in range(k):
            d = root / leaf / f"{bucket_col}={b}"
            d.mkdir(parents=True)
            (d / "data_0.parquet").touch()


WIKI_LEVELS = [
    {"column": "ngram_size", "type": "partition"},
    {"column": "country", "type": "entity"},
    {"column": "bucket", "type": "hash_bucket"},
]

REDDIT_LEVELS = [
    {"column": "n", "type": "partition"},
    {"column": "lang", "type": "partition"},
    {"column": "ngram_bucket", "type": "hash_bucket"},
]


def test_entity_shape_round_trip(tmp_path):
    _mktree(tmp_path, {
        "ngram_size=1/country=A": ("bucket", 2),
        "ngram_size=1/country=B": ("bucket", 4),
        "ngram_size=2/country=A": ("bucket", 2),
    })
    hb = _derive_bucket_config(str(tmp_path), WIKI_LEVELS)
    assert hb["default_count"] == 2
    assert hb["overrides"] == {"1/B": 4}

    ds = SimpleNamespace(level_order=WIKI_LEVELS)
    key_b = bucket_override_key(ds, entity_value="B", filter_vals={"ngram_size": 1})
    assert resolve_bucket_count(hb, key_b) == 4
    key_a = bucket_override_key(ds, entity_value="A", filter_vals={"ngram_size": 1})
    assert resolve_bucket_count(hb, key_a) == 2


def test_partition_only_shape_round_trip(tmp_path):
    """The reddit shape — regression for the entity-less bug."""
    _mktree(tmp_path, {
        "n=1/lang=en": ("ngram_bucket", 4),
        "n=1/lang=gn": ("ngram_bucket", 1),
        "n=2/lang=en": ("ngram_bucket", 4),
    })
    hb = _derive_bucket_config(str(tmp_path), REDDIT_LEVELS)
    assert hb["default_count"] == 4
    assert hb["overrides"] == {"1/gn": 1}

    ds = SimpleNamespace(level_order=REDDIT_LEVELS)
    key_gn = bucket_override_key(ds, filter_vals={"n": 1, "lang": "gn"})
    assert resolve_bucket_count(hb, key_gn) == 1
    key_en = bucket_override_key(ds, filter_vals={"n": 1, "lang": "en"})
    assert resolve_bucket_count(hb, key_en) == 4


def test_k_agreement_every_leaf(tmp_path):
    """Property: resolved count == directories on disk, for every leaf."""
    leaves = {
        "n=1/lang=en": ("ngram_bucket", 8),
        "n=1/lang=es": ("ngram_bucket", 2),
        "n=1/lang=gn": ("ngram_bucket", 1),
        "n=2/lang=en": ("ngram_bucket", 8),
        "n=2/lang=gn": ("ngram_bucket", 1),
    }
    _mktree(tmp_path, leaves)
    hb = _derive_bucket_config(str(tmp_path), REDDIT_LEVELS)
    ds = SimpleNamespace(level_order=REDDIT_LEVELS)

    for leaf, (_col, k_written) in leaves.items():
        n, lang = (part.split("=")[1] for part in leaf.split("/"))
        key = bucket_override_key(ds, filter_vals={"n": n, "lang": lang})
        assert resolve_bucket_count(hb, key) == k_written, leaf


def test_missing_level_value_falls_back_to_default(tmp_path):
    _mktree(tmp_path, {"n=1/lang=en": ("ngram_bucket", 4)})
    hb = _derive_bucket_config(str(tmp_path), REDDIT_LEVELS)
    ds = SimpleNamespace(level_order=REDDIT_LEVELS)
    # lang missing → key is None → default, never a wrong override
    assert bucket_override_key(ds, filter_vals={"n": 1}) is None
    assert resolve_bucket_count(hb, None) == hb["default_count"]
