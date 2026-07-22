---
name: storywrangler-sveltekit
description: Use the Storywrangler registry to access the Vermont Complex Systems datasets and instruments from a SvelteKit frontend using remote functions. Discover what data is available, its shape, and how it can be used out of the box with text-based instruments for studying collective attention — the allotaxonometer, wordshift, and term time series. Load this when building a SvelteKit app against Storywrangler: enforcing type-safe queries, handling instrument errors, and keeping the user in the loop on which dataset and instrument to use. For deep query craft load storywrangler-analyst; for submitting data load storywrangler-submitter.
---

# Using Storywrangler from a SvelteKit app

Storywrangler is a data platform with two layers: a **registry of datasets**
(corpora like wikimedia n-grams, reddit, babynames) and **instruments** —
analysis endpoints layered on those datasets (allotaxonometer, wordshift, term
time series, top n-grams). Your app picks a dataset, calls an instrument on it,
and draws the result.

Two things you never carry in your head — both live in the **MCP** and drift
over time:

- **the dataset catalog** → `list-datasets`
- **an instrument's exact arguments** → `get-dataset`

The SvelteKit remote-function mechanics (query vs prerender, validation,
rendering) are assumed knowledge — the Svelte remote-functions skill and MCP
own them. This skill owns the Storywrangler practical layer, and it keeps the
**user in the loop** at the two decisions that are theirs: which dataset, which
instrument.

## Start from the registry — don't assume a dataset

When a request is vague about *which* data ("show storywrangler data", "add a
wordshift"), don't silently default to a corpus. List what exists with the MCP
`list-datasets`, surface the options, and let the user choose. Then
`get-dataset` shows that dataset's instruments, columns, filter dimensions,
entity mapping, and date availability. Confirm the dataset and the slice before
wiring anything.

## Pick the instrument from the user's question

The instrument follows from what the user is trying to show:

- **Allotaxonometer** — compare two systems (rank-turbulence divergence):
  entity vs entity, date vs date, or filter vs filter. *"How does A differ from
  B?"* A rich, heavier response (diamond + wordshift + balance).
- **Wordshift / RTD** — explain a single date-vs-date shift for one entity.
  *"What drove the change?"* Lightweight and fast.
- **Top n-grams / term series** — a leaderboard for a slice, or one term over
  time.

Ask which comparison they're after; the instrument choice falls out of it. The
endpoint path and its exact arguments (entity ids, date formats, filter dims,
limits) are a `get-dataset` lookup — read them there, don't guess param names.

## Wire the chosen instrument

Deliver the call as a SvelteKit remote function (the Svelte skill/MCP covers the
*how*). The parts that are Storywrangler-specific:

- **Public read, server-side.** Instruments need no auth; fetch them from the
  server half of the remote function.
- **Map the error surface to UI.** Instruments answer **404** (no data for that
  entity/date), **400** (bad filter value), **503** (instrument library down).
  Turn each into a real state, not a forever-spinner.
- **Discovery-first before hardcoding.** Resolve entities and check date
  availability (via the MCP, or `storywrangler-analyst`) before baking an
  `entity` or `date` in — otherwise the page 404s for no reason.
- **Large, sanitized payloads.** Responses can be big; bound them with the
  instrument's limit params (names via `get-dataset`). The server rewrites
  non-finite numbers — `NaN` → `null`, `±Infinity` → the strings `"Infinity"` /
  `"-Infinity"` — so treat divergence / measure fields as possibly-string.

A minimal shape — validate the argument, fetch server-side, map status. The
endpoint and params here are **illustrative**; confirm the real ones with
`get-dataset`:

```ts
// allotax.remote.ts
import { query } from '$app/server';
import { error } from '@sveltejs/kit';
import { STORYWRANGLER_URL } from '$env/static/private';
import * as v from 'valibot';

export const getAllotax = query(
  v.object({ domain: v.string(), dataset: v.string(), entity: v.string(), entity2: v.string(), dates: v.string(), dates2: v.string() }),
  async (args) => {
    const url = new URL(`${STORYWRANGLER_URL}/storywrangler/allotax`);
    url.search = new URLSearchParams(args).toString();
    const res = await fetch(url); // public read, no auth
    if (res.status === 404) error(404, 'No data for that entity or date range.');
    if (!res.ok) error(502, `Instrument error (${res.status}).`);
    return res.json();
  },
);
```
