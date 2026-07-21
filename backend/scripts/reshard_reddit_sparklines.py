"""Re-shard the reddit per-term timeseries precompute into mmh3 hash buckets.

Input   /netfiles/wikimedia_snapshots/reddit_agg/ts/n={n}/lang={lang}/0*.parquet
        (ngram-sorted range files; the ts_index.parquet files are ignored)
Output  {OUT_ROOT}/n={n}/lang={lang}/ngram_bucket={b}/*.parquet
        (plain parquet — no ducklake; ngram-sorted within each bucket, so
        row-group pruning still applies inside a bucket)

Buckets use the platform's single source of truth
(storywrangler_schemas.hashing.assign_bucket: mmh3 seed 0, sign-cleared),
so the query layer routes to them with the same function. Bucket counts are
sized per leaf from data volume; the server derives default_count/overrides
automatically at registration (_derive_bucket_config) — nothing is declared
by hand.

Resumable: a leaf with a _DONE marker is skipped, so the job can be
re-launched after interruption. ts/ is read-only throughout; cut over by
registering the new root once the run finishes.

Run (long job — schedule it, e.g. per-n screen/sbatch):
    uv run python backend/scripts/reshard_reddit_sparklines.py [--only n=1/lang=gn]
"""

import argparse
import math
import sys
from pathlib import Path

import duckdb

from storywrangler_schemas.hashing import assign_bucket

IN_ROOT = Path("/netfiles/wikimedia_snapshots/reddit_agg/ts")
OUT_ROOT = Path("/netfiles/wikimedia_snapshots/reddit_agg/sparklines")
TARGET_BUCKET_BYTES = 2 * 1024**3  # ~2 GiB per bucket → en/1grams lands near 64


def leaf_bytes(leaf: Path) -> int:
    return sum(f.stat().st_size for f in leaf.glob("0*.parquet"))


def bucket_count(size: int) -> int:
    return max(1, min(64, math.ceil(size / TARGET_BUCKET_BYTES)))


def reshard_leaf(leaf: Path, out_leaf: Path, k: int) -> None:
    """One (n, lang) leaf → ngram_bucket={0..k-1}/ dirs, ngram-sorted."""
    conn = duckdb.connect()
    conn.execute("SET preserve_insertion_order = true")

    # Bucket assignment must be the platform's mmh3 — computed in Python over
    # the leaf vocabulary (C-speed, millions/s), joined back in DuckDB.
    vocab = [r[0] for r in conn.execute(
        f"SELECT DISTINCT ngram FROM read_parquet('{leaf}/0*.parquet')"
    ).fetchall()]
    conn.execute("CREATE TEMP TABLE bucket_map (ngram VARCHAR, ngram_bucket INTEGER)")
    conn.executemany(
        "INSERT INTO bucket_map VALUES (?, ?)",
        [(t, assign_bucket(t, k)) for t in vocab],
    )

    out_leaf.mkdir(parents=True, exist_ok=True)
    conn.execute(f"""
        COPY (
            SELECT d.* EXCLUDE (lang, n), m.ngram_bucket
            FROM read_parquet('{leaf}/0*.parquet') d
            JOIN bucket_map m USING (ngram)
            ORDER BY m.ngram_bucket, d.ngram, d.date
        ) TO '{out_leaf}' (FORMAT PARQUET, PARTITION_BY (ngram_bucket),
                           OVERWRITE_OR_IGNORE, ROW_GROUP_SIZE 122880)
    """)
    conn.close()
    (out_leaf / "_DONE").write_text(f"buckets={k} vocab={len(vocab)}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="restrict to one leaf, e.g. 'n=1/lang=gn'")
    args = ap.parse_args()

    leaves = sorted(p.parent for p in IN_ROOT.glob("n=*/lang=*/0000.parquet"))
    if args.only:
        leaves = [l for l in leaves if str(l.relative_to(IN_ROOT)) == args.only]
    if not leaves:
        print("no leaves matched", file=sys.stderr)
        return 1

    for leaf in leaves:
        rel = leaf.relative_to(IN_ROOT)
        out_leaf = OUT_ROOT / rel
        if (out_leaf / "_DONE").exists():
            print(f"skip {rel} (done)")
            continue
        size = leaf_bytes(leaf)
        k = bucket_count(size)
        print(f"reshard {rel}: {size/1e9:.1f} GB → {k} buckets", flush=True)
        reshard_leaf(leaf, out_leaf, k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
