"""
Seed the entity_graph table with a prototype cross-namespace edge set.

Demonstrates the join chain that makes cross-dataset federation possible:

    oaa.papers / oaa.coauthors / oaa.training
        ego_author_id  →  openalex:A...   (entity_namespace = "openalex")
            │
            │  affiliated_with  (from OpenAlex API: author.affiliations)
            ▼
        openalex:I...  (institution)
            │
            │  same_as  (from OpenAlex API: institution.ids.wikidata)
            ▼
        wikidata:Q...  (institution on Wikidata)
            │
            │  country  (from OpenAlex API: institution.country_code → Wikidata Q)
            ▼
        wikidata:Q30   ← shared namespace with babynames!
            │
            └── babynames entity_mapping → local_id "united_states"

Once this chain exists in entity_graph, a platform query like:
    "compare babynames in the countries where UVM researchers are based"
can be answered by:
    1. Collecting openalex:A... IDs from oaa.papers
    2. BFS to wikidata:Q (country) for each author
    3. Querying babynames with those wikidata:Q IDs

Run against a live backend:
    python scripts/seed_entity_graph.py --api-url http://localhost:8000 --api-key <key>

Or use the /admin/registry/entity-graph endpoint directly.
"""

import argparse
import httpx

# ── Prototype edges ────────────────────────────────────────────────────────────
# UVM (University of Vermont) as a worked example.
# Real data would be populated by an enrichment job calling the OpenAlex API
# for each openalex:A entity in oaa.*/entities.

SEED_EDGES = [
    # Institution identity: OpenAlex ↔ Wikidata
    # OpenAlex: https://openalex.org/I26873012
    # Wikidata: https://www.wikidata.org/wiki/Q1068
    {
        "subject_id": "openalex:I26873012",
        "predicate":  "same_as",
        "object_id":  "wikidata:Q1068",
        "source":     "openalex",
    },
    # Institution → country
    # UVM is in the United States (wikidata:Q30)
    {
        "subject_id": "openalex:I26873012",
        "predicate":  "country",
        "object_id":  "wikidata:Q30",
        "source":     "openalex",
    },

    # A second institution to show the pattern generalises
    # MIT: openalex:I63966007, wikidata:Q49108
    {
        "subject_id": "openalex:I63966007",
        "predicate":  "same_as",
        "object_id":  "wikidata:Q49108",
        "source":     "openalex",
    },
    {
        "subject_id": "openalex:I63966007",
        "predicate":  "country",
        "object_id":  "wikidata:Q30",
        "source":     "openalex",
    },

    # Author → institution edges would be populated per-researcher from OpenAlex API.
    # Example placeholder (not a real OpenAlex author ID):
    #   {"subject_id": "openalex:A5002034958", "predicate": "affiliated_with",
    #    "object_id": "openalex:I26873012", "source": "openalex"}
    #
    # An enrichment script would do:
    #   for each entity_id in GET /registry/open-academic-analytics/oaa.papers/adapter:
    #       r = httpx.get(f"https://api.openalex.org/authors/{entity_id.split(':')[1]}")
    #       for aff in r.json()["affiliations"]:
    #           POST /admin/registry/entity-graph  {subject_id: entity_id,
    #                                               predicate: "affiliated_with",
    #                                               object_id: f"openalex:{aff['institution']['id']}"}
]


def seed(api_url: str, api_key: str) -> None:
    url = f"{api_url.rstrip('/')}/admin/registry/entity-graph"
    r = httpx.post(
        url,
        json=SEED_EDGES,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    print(f"Seeded {data['edges_upserted']} edges into entity_graph.")
    print()
    print("To verify the OAA → babynames join chain, query:")
    print(f"  GET {api_url}/registry/entity-graph/path"
          "?from_id=openalex:I26873012&to_namespace=wikidata")
    print()
    print("Expected path:")
    print("  openalex:I26873012 --same_as--> wikidata:Q1068")
    print("  wikidata:Q1068     --country--> wikidata:Q30")
    print()
    print("wikidata:Q30 is United States — the same entity used in babynames.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed entity_graph prototype edges.")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--api-key", required=True)
    args = parser.parse_args()
    seed(args.api_url, args.api_key)
