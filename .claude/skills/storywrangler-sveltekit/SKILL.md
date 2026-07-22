---
name: storywrangler-sveltekit
description: Use the Storywrangler registry to access the Vermont Complex Systems datasets and instruments from a SvelteKit frontend using remote functions. Discover what data is available, its shape, and how to use it out of the box, directly or through text-based instruments for studying collective attention such as the allotaxonometer and wordshift. Load this when building a SvelteKit app against Storywrangler to enforce type-safe queries, handle instrument errors, and keep the user in the loop on which dataset and whether to use an instrument. For deep query craft load storywrangler-analyst; for submitting data load storywrangler-submitter.
---

# Using Storywrangler from a SvelteKit app

Storywrangler is a data platform with two layers: a **registry of datasets**
(corpora like wikimedia n-grams, reddit, babynames) and **instruments** —
computational analyses layered on those datasets, like the allotaxonometer and
wordshift. Your app picks a dataset and either reads its data directly or runs
an instrument over it, then draws the result.

You never carry the specifics in your head — they live on the **MCP**, which has
two discovery surfaces:

- **Docs** (`list-sections`, then `get-documentation`) — the platform guides and
  the instrument / endpoint reference: what an instrument does, its parameters,
  response shape, examples, and use cases. The endpoint reference lives under
  `api-reference/…` (e.g. `api-reference/storywrangler`). Start here to
  understand *what exists and how it works*.
- **Registry** (`list-datasets`, then `get-dataset`) — the live catalog: which
  datasets exist, and for one dataset its queryable dimensions, valid filter
  values, and date availability. This is *what data exists and which values are
  valid*.

Two boundaries keep this skill from drifting:

- **SvelteKit mechanics** (remote functions, query vs prerender, validation,
  rendering) belong to the Svelte skills and MCP. That API is still evolving —
  get the current code from them, don't reproduce it here.
- **Instrument and dataset specifics** belong to the MCP surfaces above. Don't
  recite a fixed list of instruments or guess params — look them up.

What this skill owns is the Storywrangler practical layer, and keeping the
**user in the loop** on the decisions that are theirs: which dataset, and
whether to use an instrument at all (and which).

## Start from the registry — don't assume a dataset

When a request is vague about *which* data ("show storywrangler data", "add a
wordshift"), don't silently default to a corpus. List what exists with
`list-datasets`, surface the options, and let the user choose. Then `get-dataset`
gives that dataset's queryable dimensions, valid filter values, entity mapping,
date availability, and `endpoint_schema` (its output shape). Confirm the dataset
and the slice before wiring anything.

## Data directly, or an instrument?

Not every app needs an instrument — often the user just wants to read and show
the dataset's own data (counts, ranks, time series). An **instrument** is a
computational analysis layered on top (the allotaxonometer, wordshift, …).

Don't assume one, and don't recite a fixed menu — the available instruments and
their use cases live in the MCP. If the user isn't sure what to build, look them
up (`get-documentation`, `api-reference/…`) and **propose** the ones whose
documented use case fits their question; let them choose.

Once the target is settled, the lookup splits across the two MCP surfaces: the
endpoint's **parameter contract** (params, response shape, examples) comes from
the API reference, and the dataset's **valid values** (which entities exist,
which dates are available, which filter dims) come from `get-dataset`. Read
both; don't guess.

## Wiring the call — the Storywrangler-specific parts

Deliver the call as a SvelteKit remote function, but the *how* (the remote-
function API, argument validation, rendering) is the Svelte skills' job — and
that API is still moving, so take the current shape from them rather than from
memory. What stays true on the Storywrangler side:

- **Public read, no auth.** The data and instrument endpoints need no key to
  consume.
- **Map the error surface to UI.** Endpoints answer **404** (no data for that
  entity/date), **400** (bad filter value), **503** (instrument library down).
  Turn each into a real state, not a forever-spinner.
- **Discovery-first before hardcoding.** Resolve entities and check date
  availability (via the MCP, or `storywrangler-analyst`) before baking an
  `entity` or `date` in — otherwise the page 404s for no reason.
- **Large, sanitized payloads.** Responses can be big; bound them with the
  endpoint's limit params (documented in the API reference). The server rewrites
  non-finite numbers — `NaN` → `null`, `±Infinity` → the strings `"Infinity"` /
  `"-Infinity"` — so treat divergence / measure fields as possibly-string.
