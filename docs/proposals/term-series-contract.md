# Proposal: a declared term-series contract (rank/freq columns) toward a generic `/storywrangler/term-series`

Status: partly shipped, partly draft.
Follows: the generic `/storywrangler/top-ngrams` work (branch `generic-ngram-endpoints`).

**Shipped** (branch `feat/generic-term-series`): the rank/freq companion columns
(`resolve_series_columns`), the generic `/storywrangler/term-series` + `/batch`
across parquet_hive / flat parquet / mongodb, the `?include=` provenance
mechanism (`type-documents` + `fetch_provenance`), and the orientation /
companion-resolution section below — the `orientation` / `role` schema fields,
lineage-based `resolve_companions`, term-series auto-resolving its type-first
sparkline (no `sparkline_dataset` needed), and role-based `?include=<role>` /
`include=all`. The implicit `"sparklines"` naming-convention fallback was
**not** kept (it was the structural sniffing this section argues against): a
sparkline must declare `orientation: type-first`, else the query uses the
correct-but-slower date-first scan. A dataset that *is itself* type-first
(bluesky's term-bucketed tree) declares the orientation on its own
registration and serves as its own fast path — the bucket read is the read,
so there is no scan fallback and a bucket miss is an honest empty series.
The explicit deprecated aliases
(`sparkline_dataset=<id>`, `include=<dataset_id>`) remain for one release.
The per-domain `/{domain}/term-series` routes are now **retired** (the
`(babynames, reddit, bluesky, twitter, wikimedia)` bespoke handlers removed; all
domains served through the generic endpoint). Fully shipped.

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

## Composition: declared provenance (`include=`)

Beyond count/rank/freq, consumers often want *what explains* a type's signal —
the underlying documents the type came from. Wikipedia has this today as a
separate hash-bucketed dataset, `top_articles_ngrams`: `(type, date) → ranked
[(article_url, score)]`. It is structurally a **type-first provenance dataset** —
same access pattern as the sparklines (bucket by type), a different payload (a
ranked document list rather than count/rank/freq). Example on disk:

```
top_articles/ngram_size=1/country=Canada/bucket=0/ducklake-*.parquet
  columns: ngram, date, article_rank, article_url, score   (long: one row per (type, date, doc))
```

This is not a Wikipedia quirk — reddit already carries the same idea inline as a
column (`top_subreddits STRUCT(subreddit, score_weighted)[]`), and twitter→top
tweets / bluesky→top posts fit the same mould: *the sources that explain a
type's signal.*

The wrong way to compose is a join baked into term-series (which is what wiki's
`include_articles` is today — bespoke, hardcoded, per-router). The right way,
two parts:

1. **Model provenance as its own generic type-first endpoint-type** — e.g.
   `type-sources`: `(type, date) → ranked [(document, score)]`. It gets a
   generic endpoint out of the box (queryable tidily on its own) and is reusable
   across domains.
2. **Compose via an opt-in, registry-*declared* `?include=`**, not a per-router
   join. The `type-series` dataset declares its provenance companion in its
   registration; `term-series?...&include=sources` resolves that companion and
   nests it, `include=` absent returns the tidy count/rank/freq. The base
   endpoint stays single-responsibility; the un-tidy nesting appears only when
   asked for.

This is the mainstream REST pattern for staying composable short of GraphQL —
Stripe `?expand[]=`, JSON:API `?include=`, OData `$expand`: opt-in server-side
expansion of *declared* relationships. It also extends an existing separation in
storywrangler: the instruments (allotax/rtd/wordshift) are already a composition
layer over the primitive "load a types-counts system," so `?include=` applies the
same primitives-vs-compositions discipline to the type-series family rather than
inventing a new concept.

Consequence for this proposal: the generic `/storywrangler/term-series` (step 2)
should carry a general, registry-declared `include=` hook rather than porting
wiki's hardcoded articles join. Wiki's `top_articles` becomes the *reference
instance* of the general mechanism; reddit's `top_subreddits` can migrate onto
the same `type-sources` model or stay inline (small structs are fine).

## Orientation and companion resolution (date-first ↔ type-first ↔ documents)

This is the answer to open question 3, and it is worth getting right *now*: the
current pairing is convention, and the convention leaks into the API surface
(the `sparkline_dataset` param, `?include=<dataset_id>`). Once consumers depend
on those, replacing them is a breaking change — so declare the relationship
before that happens.

### The problem

A corpus (e.g. `wikimedia/ngrams`, or a hypothetical `twitter/nfl-tweets`) is
served by several *physical* datasets:

- a **time-first** `types-counts` tree (date-partitioned) — feeds top-ngrams,
  allotax, rtd, wordshift, and the term-series *slow fallback*;
- a **type-first** `types-counts` tree (hash-bucketed by type) — the sparkline,
  the term-series *fast path*;
- zero or more **`type-documents`** provenance sets (inherently type-first) —
  the `?include=` sources.

Today the platform does not *know* these are related. The generic term-series
finds the type-first form via the `sparkline_dataset` query param (defaulting to
the name `"sparklines"`), and the sparklines carry no `endpoint_schema` at all —
they are invisible companions discovered by naming convention.

### Model: separate datasets, declared orientation, paired via lineage

These forms have **independent lifecycles** — the DuckLake sparklines refresh
nightly while the raw ngrams sync lags — so they version and update separately.
That rules out unifying them under one `dataset_id` (a `dataset_id` +
orientation sub-key just becomes `(id, orientation, version)`, i.e. the current
registry with a migrated primary key, for no gain). Keep them as **separate
registry datasets**; the primary (time-first) `dataset_id` is the name callers
use, and the platform resolves the other forms.

Two declarations, one of which is already made:

1. **`orientation: "time-first" | "type-first"`** on `types-counts`
   (default `"time-first"`). The only genuinely new field. It makes "this is the
   type-first form" explicit rather than sniffed from `transform.hash_bucket`
   (structural sniffing is fragile — a small-vocabulary type-first dataset might
   be a sorted flat file with no bucket). `type-documents` needs no orientation
   (it is inherently type-first).

2. **Pairing reuses `lineage.derived_from`** — which the sparkline and
   `top_articles` *already declare* (`derived_from: ["wikimedia/ngrams"]`). So
   companions are deduced from *declared provenance*, never from structure:
   - term-series' fast path = the `types-counts` dataset with
     `orientation: type-first` whose `derived_from` includes the primary;
   - `?include=` sources = the `type-documents` datasets whose `derived_from`
     includes the primary.

   Resolution is a filter over the domain's datasets (a handful per domain), so
   it is cheap. It is also **decoupled**: a sparkline or a provenance set is
   added later by registering it with `derived_from`, with no change to the
   primary — which matches the independent lifecycles.

### API surface this replaces

- term-series **drops `sparkline_dataset`**; it resolves the type-first
  companion itself. The caller only names `dataset=<primary>`.
- `?include=` stops naming raw dataset ids. Each `type-documents` companion
  declares a **`role`** (e.g. `articles`, `subreddits`); the platform knows a
  corpus's provenance companions, so `?include=articles` (or `include=all`)
  reads cleanly and there is no leaky id in the surface. `role` is the one
  remaining sub-decision — the alternative is `?include=<companion dataset_id>`,
  which works but re-introduces the leak. Recommendation: `role`.

### Registration shape

`(twitter, nfl-tweets)` becomes three datasets, every endpoint routed off
`dataset=nfl-tweets`:

```
nfl-tweets             types-counts   orientation=time-first     (caller names this)
nfl-tweets-sparklines  types-counts   orientation=type-first     derived_from=[twitter/nfl-tweets]
nfl-tweets-articles    type-documents role=articles              derived_from=[twitter/nfl-tweets]
```

### Migration

Additive. `orientation` defaults to `time-first`, so existing time-first
datasets need no change; sparklines re-register with `orientation: type-first`
(they already declare `derived_from`) to regain the fast path; `type-documents`
datasets add a `role` to be addressable as `?include=<role>`. The explicit
`sparkline_dataset`/`?include=<id>` aliases keep working (deprecated, one
release); the implicit `"sparklines"` name-convention was dropped, so an
un-migrated sparkline degrades to the date-first scan rather than being sniffed
by name.

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
3. **Date-first ↔ type-first pairing.** *Resolved* — see "Orientation and
   companion resolution": an explicit `orientation` field plus lineage-based
   companion deduction, replacing the `sparkline_dataset` param and
   `?include=<dataset_id>`.

## Rollout

1. Land this proposal's schema fields + `resolve_series_columns` + omit-based
   `series_entry`; the existing per-domain routers adopt the resolver (no
   behavior change — they already return the same columns).
2. Add `/storywrangler/term-series` + `/batch` (registry-driven), keeping the
   per-domain routers.
3. Retire per-domain term-series once the generic endpoint is at parity, with
   wiki's `top_articles` re-expressed as a declared `type-documents` provenance
   dataset behind the general `?include=` mechanism (not a bespoke join).
   **Done** — bespoke handlers removed; `wikimedia/ngrams-articles` (role
   `articles`) is the reference `?include=` companion.
