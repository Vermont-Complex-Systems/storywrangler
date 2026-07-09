#!/usr/bin/env python3
"""Cache real Storywrangler API responses for the home-page LiveDemo.

The home page shows a two-curl workflow (list the catalog, then pull a term's
trajectory) ending in a d3 chart. To keep the hero reliable we don't fetch at
runtime — we cache authentic responses here and import them as JSON. Re-run to
refresh:

    python scripts/fetch_demo_data.py

Writes:
    src/lib/data/demo-registry.json    — [{catalog, domain, dataset_id, type}]
    src/lib/data/demo-termseries.json  — {entity, terms: [{term, series: [{date, freq}]}]}
    src/lib/data/demo-allotax.json     — {title, sys1: [{types, counts}], sys2: [...]}
"""

import json
import ssl
import urllib.request
from pathlib import Path

BASE = "https://api.storywrangler.uvm.edu"
# uvm.edu cert currently mismatches (see CLAUDE.md); skip verification for this
# offline cache step only.
CTX = ssl._create_unverified_context()
OUT = Path(__file__).resolve().parent.parent / "src" / "lib" / "data"

TERMS = ["Trump", "Harris"]
ENTITY = "wikidata:Q30"  # United States


def get(path: str):
    with urllib.request.urlopen(BASE + path, context=CTX, timeout=30) as r:
        return json.load(r)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    reg = get("/registry/")
    datasets = [
        {
            "catalog": d.get("catalog", "vcsi"),
            "domain": d["domain"],
            "dataset_id": d["dataset_id"],
            "type": (d.get("endpoint_schema") or {}).get("type"),
        }
        for d in reg["datasets"]
    ]
    (OUT / "demo-registry.json").write_text(json.dumps(datasets, indent=2) + "\n")

    batch = get(
        f"/wikimedia/term-series/batch?entity={ENTITY}"
        f"&types={','.join(TERMS)}&granularity=daily&n=1&include_articles=false"
    )
    results = batch["results"]
    terms = [
        {
            "term": t,
            "series": [
                {"date": p["date"], "rank": p["rank"], "freq": p["freq"]} for p in results[t]
            ],
        }
        for t in TERMS
    ]
    payload = {"entity": ENTITY, "terms": terms}
    (OUT / "demo-termseries.json").write_text(json.dumps(payload) + "\n")

    # Allotaxonometer systems: the two ranked ngram distributions the
    # allotaxonometer-ui compares (election day vs the Charlie Kirk spike).
    d1, d2 = "2024-11-06", "2025-09-10"
    allo = get(
        f"/wikimedia/top-ngrams?dates={d1}&dates2={d2}"
        f"&locations={ENTITY}&granularity=daily&n=1&limit=2000"
    )
    allotax = {
        "title": [f"Wikipedia (US) · {d1}", f"Wikipedia (US) · {d2}"],
        "sys1": [{"types": x["types"], "counts": x["counts"]} for x in allo[d1]],
        "sys2": [{"types": x["types"], "counts": x["counts"]} for x in allo[d2]],
    }
    (OUT / "demo-allotax.json").write_text(json.dumps(allotax) + "\n")

    npts = sum(len(t["series"]) for t in terms)
    print(
        f"wrote {len(datasets)} datasets, {len(terms)} terms / {npts} points, "
        f"allotax {len(allotax['sys1'])}x{len(allotax['sys2'])} ngrams to {OUT}"
    )


if __name__ == "__main__":
    main()
