# Proposal: a declared term-series contract (rank/freq columns) toward a generic `/storywrangler/term-series`

Status: draft / for discussion
Follows: the generic `/storywrangler/top-ngrams` work (branch `generic-ngram-endpoints`).

## Problem

`top-ngrams` generalized cleanly into one registration-driven endpoint because a
top-ngrams row needs exactly **one** measure — `SUM(count_column)` — and
`count_column` is already declared in `endpoint_schema` and selected per-request
via `?weight=`.

`term-series` did not generalize, because a term-series row carries **three**
measures, not one:

```python
series_entry(date, count, rank, freq) -> {"date", "counts", "rank", "freq"}
```

The `count` is registry-driven (same `count_column` menu, same `?weight=`). But
`rank` and `freq` are *companions* of the chosen count, and the rule mapping a
count column to its rank/freq columns lives only in per-router Python
(`_series_cols` in wikimedia / reddit / bluesky), in three different forms:

| dataset | count → rank | count → freq |
|---|---|---|
| reddit | **canonical** single `rank`, independent of weight | strip `_weighted`, add `_freq` |
| bluesky | per-measure (`count`→`rank`, `count_all`→`rank_all`) | per-measure (`count`→`freq`, `count_all`→`freq_all`) |
| wikimedia | fixed `pv_rank` | fixed `pv_freq` |

The reddit vs bluesky split is not a naming inconsistency — it is a genuine
*semantic* difference: reddit's rank is a canonical pipeline-side ranking that
does **not** change with the selected weight (see CLAUDE.md, "Stored rank
columns are canonical"), while bluesky's rank tracks the weight. Only the
dataset knows which; a generic endpoint cannot derive it. Deriving by naming
heuristic silently returns `rank: 0, freq: 0` where real values exist (e.g.
reddit's canonical `rank` and `comments_controversy_freq`) — the same
quiet-wrongness we removed elsewhere (dates silent-ignore, bluesky subtree scan).

## Why count/rank/freq is the right (and complete) set

These three are exactly the measures that require the **whole per-period
distribution** to compute:

- `count` — the magnitude for the (type, period). *Not always a raw count:*
  reddit's is a weighting/attention score, wikimedia's is pageviews. "counts"
  is a misnomer for "the selected measure".
- `rank` — the type's ordinal position among **all** types that period.
- `freq` — `count` divided by **the period's total** (a normalized rate).

Rank and freq cannot be reconstructed from the returned series alone, nor from
the type-first sparkline bucket (which holds one term, not the period's whole
distribution). So they must be precomputed and stored. Everything else one might
want on a term timeseries — smoothing, a windowed z-score, normalizing within
the returned range, rank-*change* — **is** derivable from the returned series,
which per the transform-boundary rule (CLAUDE.md) is frontend territory. So the
contract is principled: *the precomputed measures you can't recompute
downstream*. A fourth field earns its place only if it is another
global-distribution precompute.

## Proposed change

Add two optional fields to `endpoint_schema`, each **a scalar or a list parallel
to `count_column`**:

```python
endpoint_schema = {
    "type": "types-counts",
    "type_column": "ngram",
    "count_column": [...],   # existing measure menu (first = default)
    "rank_column": ...,      # NEW: str | list[str] | None
    "freq_column": ...,      # NEW: str | list[str] | None
}
```

Resolution, given the `?weight=` chosen index *i* into `count_column`:

- `count = count_column[i]`
- `rank  = rank_column`   if scalar, else `rank_column[i]`, else omit
- `freq  = freq_column`   if scalar, else `freq_column[i]`, else omit

The scalar-or-list distinction is exactly what expresses reddit's
canonical-rank vs bluesky's per-measure-rank:

| dataset | `count_column` | `rank_column` | `freq_column` |
|---|---|---|---|
| reddit | `[all_score_weighted, …, submissions_unweighted]` (8) | `"rank"` (scalar) | `[all_score_freq, …, submissions_unweighted_freq]` (8) |
| bluesky | `[count, count_all]` | `[rank, rank_all]` | `[freq, freq_all]` |
| wikimedia | `pv_count` | `pv_rank` | `pv_freq` |

Verified against the live `data_schema` of each dataset: every parallel entry
already exists on disk, so this is a **registration-metadata change only** — no
re-materialization.

### Honesty rules

1. **Omit, don't zero-fill.** A dataset that declares no `rank_column`/
   `freq_column` returns `{date, counts}` — the key is absent, not `0`.
   "No rank" must be distinguishable from "rank 0". (Today `series_entry`
   always emits `rank: 0, freq: 0`.)
2. **Validation.** A list-form companion must be the same length as
   `count_column`; every named column must exist in the introspected
   `data_schema`. Enforced at registration (fail fast), mirrored in the MCP
   `validate-submission` dry-run.

## What this unlocks

- `resolve_series_columns(dataset, weight)` — a single registry-driven resolver
  replacing the three per-router `_series_cols`.
- A fully generic `/storywrangler/term-series` (and `/batch`) parallel to
  `/storywrangler/top-ngrams`: fast lookup on the type-first dataset + filtered
  read of the date-first companion, with `select_cols` derived from the
  registry. The per-domain term-series endpoints can then retire, except where a
  dataset needs bespoke enrichment (wikimedia's `top_articles`), which stays a
  hook or a separate route.
- New datasets (e.g. `bluesky/nfl-posts`) get term-series for free by declaring
  the companions, or a clean count-only series by declaring nothing.

## Open questions

1. **Rename `counts` → `value`/`measure` in the response?** It is the accurate
   name (the field is not always a count). But it is the public response
   contract (frontend sparklines, SDK `.df()`), so a rename is breaking and
   should be versioned. Recommendation: keep `counts` for now, document that it
   means "the selected measure", decide the rename separately.
2. **Batch fallback strategy** for the generic endpoint: per-missing-term
   (wikimedia, precise) vs all-or-nothing (reddit/bluesky, avoids triggering an
   expensive dist-tree scan for one rare term). Likely a `fallback=` knob tied
   to how costly the date-first scan is, rather than a single hardcoded choice.
3. **Date-first ↔ type-first pairing.** Today the convention is `ngrams`
   (date-first) + `sparklines` (type-first). Make this an explicit registration
   field, or keep the naming convention?

## Rollout

1. Land this proposal's schema fields + `resolve_series_columns` + omit-based
   `series_entry`; the existing per-domain routers adopt the resolver (no
   behavior change — they already return the same columns).
2. Add `/storywrangler/term-series` + `/batch` (registry-driven), keeping the
   per-domain routers.
3. Retire per-domain term-series once the generic endpoint is at parity,
   leaving only bespoke enrichment routes (wikimedia articles).
