"""OpenAPI response documentation for domain routers.

Static `openapi_extra` payloads — response schemas, examples, and
frontend/performance notes — kept out of the routers so endpoint logic
stays readable. Constants are named <ROUTER>_<ENDPOINT_FUNCTION>.
"""

WIKIMEDIA_GET_TOP_NGRAMS = {
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "array",
                                "description": "N-gram frequency entries sorted by count descending.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "types": {"type": "string", "description": "The n-gram string"},
                                        "counts": {"type": "integer", "description": "Total occurrence count over the date range"},
                                    },
                                },
                            },
                            "metadata": {
                                "type": "object",
                                "description": "Request metadata echoed back",
                                "properties": {
                                    "granularity": {"type": "string", "description": "Granularity used (daily/weekly/monthly)"},
                                    "location": {"type": "string", "description": "Entity ID used"},
                                },
                            },
                        },
                    },
                    "example": {
                        "data": [
                            {"types": "the", "counts": 12345678},
                            {"types": "of", "counts": 9876543},
                            {"types": "a", "counts": 8234567},
                        ],
                        "metadata": {"granularity": "daily", "location": "wikidata:Q30"},
                    },
                }
            },
        }
    }
}

WIKIMEDIA_LIST_REVISION_ARTICLES = {
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "articles": {
                                "type": "array",
                                "description": "Articles with extracted revision histories",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "identifier": {"type": "string", "description": "Article identifier (slug)"},
                                        "revision_count": {"type": "integer", "description": "Number of revisions extracted"},
                                    },
                                },
                            },
                            "total": {"type": "integer", "description": "Total number of matching articles returned"},
                        },
                    },
                    "example": {
                        "articles": [
                            {"identifier": "Cat", "revision_count": 142},
                            {"identifier": "Dog", "revision_count": 98},
                        ],
                        "total": 2,
                    },
                }
            },
        }
    }
}

WIKIMEDIA_GET_REVISION_DELTAS = {
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "revisions": {
                                "type": "array",
                                "description": "Ordered revision history (oldest first). First entry is the full token map; subsequent entries contain only changed tokens.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "revision_id": {"type": "string", "description": "Wikipedia revision ID"},
                                        "name": {"type": "string", "description": "Article title"},
                                        "date_modified": {"type": "string", "description": "ISO 8601 modification date"},
                                        "revision_comment": {"type": "string", "description": "Edit summary"},
                                        "categories": {"type": "array", "description": "List of article categories"},
                                        "token_diff": {"type": "string", "description": "JSON-encoded delta map: token → new count (0 = removed)"},
                                    },
                                },
                            },
                        },
                    },
                    "example": {
                        "revisions": [
                            {
                                "revision_id": "1234567890",
                                "name": "Cat",
                                "date_modified": "2024-01-15",
                                "revision_comment": "/* Breeds */ Added Persian section",
                                "categories": ["Cats", "Mammals", "Pets"],
                                "token_diff": '{"cat": 3, "breed": 5, "persian": 1}',
                            }
                        ]
                    },
                }
            },
        }
    }
}

WIKIMEDIA_TERM_SERIES = {
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "The n-gram term that was looked up (echoed back).",
                            },
                            "latest_available_date": {
                                "type": "string",
                                "format": "date",
                                "description": "Most recent date with data for this entity (YYYY-MM-DD). Use this to default the date picker in the UI.",
                            },
                            "series": {
                                "type": "array",
                                "description": "Time series entries, one per date, sorted chronologically.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "date": {"type": "string", "format": "date", "description": "Date (YYYY-MM-DD)"},
                                        "counts": {"type": "integer", "description": "Total weighted page-view count for this term on this date (sum across all Wikipedia articles containing the term)"},
                                        "rank": {"type": "integer", "description": "Rank by page-view count on this date (1 = most viewed term). 0 means not ranked."},
                                        "top_articles": {
                                            "type": "array",
                                            "description": "Top 10 Wikipedia articles contributing most page views to this term on this date. Only present when include_articles=true. Each entry is [url, score]. Empty array if no article data is available for this term on this date.",
                                            "items": {
                                                "type": "array",
                                                "prefixItems": [
                                                    {"type": "string", "description": "Full Wikipedia article URL"},
                                                    {"type": "number", "description": "Contribution score (higher = more page views attributed to this article for the term)"},
                                                ],
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "examples": {
                        "with_articles": {
                            "summary": "Term with top articles (include_articles=true, default)",
                            "value": {
                                "type": "Trump",
                                "latest_available_date": "2026-04-20",
                                "series": [
                                    {
                                        "date": "2026-04-19",
                                        "counts": 41964675,
                                        "rank": 487,
                                        "top_articles": [
                                            ["https://en.wikipedia.org/wiki/Donald_Trump", 255.07],
                                            ["https://en.wikipedia.org/wiki/Donald_Trump_Jr.", 127.83],
                                            ["https://en.wikipedia.org/wiki/Lara_Trump", 123.68],
                                        ],
                                    },
                                    {
                                        "date": "2026-04-20",
                                        "counts": 45655115,
                                        "rank": 455,
                                        "top_articles": [
                                            ["https://en.wikipedia.org/wiki/Donald_Trump", 282.65],
                                            ["https://en.wikipedia.org/wiki/Kash_Patel", 168.08],
                                            ["https://en.wikipedia.org/wiki/Vanessa_Trump", 136.84],
                                        ],
                                    },
                                ],
                            },
                        },
                        "without_articles": {
                            "summary": "Sparkline only (include_articles=false)",
                            "value": {
                                "type": "Trump",
                                "latest_available_date": "2026-04-20",
                                "series": [
                                    {"date": "2026-04-19", "counts": 41964675, "rank": 487},
                                    {"date": "2026-04-20", "counts": 45655115, "rank": 455},
                                ],
                            },
                        },
                    },
                }
            },
        }
    },
    "x-performance": {
        "fast_path": "~20-70ms for terms in the precomputed vocabulary (~65K terms including top 10K by rank + RTD-divergent terms)",
        "slow_fallback": "~3-5s for arbitrary terms not in the vocabulary (scans daily partition files)",
        "sparkline_only": "~20ms with include_articles=false (skips the articles file entirely)",
    },
    "x-frontend-notes": {
        "term_case_sensitivity": "Terms are case-sensitive. 'COVID' and 'covid' are different lookups. The sparkline vocabulary stores original case from Wikipedia page views.",
        "include_articles_usage": "Set include_articles=false when rendering sparkline charts without article tooltips (2x faster). Only request articles when the user hovers/clicks to see contributing Wikipedia pages.",
        "top_articles_coverage": "top_articles is populated for all vocabulary terms (~65K) on all dates. Empty array means the source data had no articles for that term on that date.",
        "window_0_means_full_history": "window=0 (default) returns the full available date range (~570 days). Use window=30 or window=90 for recent data.",
        "empty_series": "If the term has no data at all, series will be an empty array.",
    },
}

WIKIMEDIA_TERM_SERIES_BATCH = {
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "results": {
                                "type": "object",
                                "description": "Map of term → time series. Keys are the requested terms (in request order). Each value is an array of date entries identical to the /term-series series format.",
                                "additionalProperties": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "date": {"type": "string", "format": "date"},
                                            "counts": {"type": "integer"},
                                            "rank": {"type": "integer"},
                                            "top_articles": {
                                                "type": "array",
                                                "description": "Only present when include_articles=true.",
                                                "items": {
                                                    "type": "array",
                                                    "prefixItems": [
                                                        {"type": "string"},
                                                        {"type": "number"},
                                                    ],
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                            "latest_available_date": {
                                "type": "string",
                                "format": "date",
                                "description": "Most recent date with data for this entity.",
                            },
                        },
                    },
                    "examples": {
                        "batch_with_articles": {
                            "summary": "Batch lookup (include_articles=true)",
                            "value": {
                                "results": {
                                    "Trump": [
                                        {"date": "2026-04-20", "counts": 45655115, "rank": 455, "top_articles": [["https://en.wikipedia.org/wiki/Donald_Trump", 282.65]]},
                                    ],
                                    "COVID": [
                                        {"date": "2026-04-20", "counts": 775676, "rank": 19105, "top_articles": []},
                                    ],
                                },
                                "latest_available_date": "2026-04-20",
                            },
                        },
                        "batch_sparkline_only": {
                            "summary": "Batch sparkline only (include_articles=false)",
                            "value": {
                                "results": {
                                    "Trump": [{"date": "2026-04-20", "counts": 45655115, "rank": 455}],
                                    "COVID": [{"date": "2026-04-20", "counts": 775676, "rank": 19105}],
                                },
                                "latest_available_date": "2026-04-20",
                            },
                        },
                    },
                }
            },
        }
    },
    "x-performance": {
        "fast_path": "~20-200ms depending on number of terms (all in precomputed vocabulary)",
        "mixed_path": "If some terms are in vocabulary and some aren't, fast terms return in ~50ms and slow terms add ~3-5s",
        "sparkline_only": "~20-40ms with include_articles=false",
    },
    "x-frontend-notes": {
        "typical_usage": "Used to fetch sparklines for multiple terms at once, e.g. all terms from an RTD wordshift comparison. Pass the wordshift types as comma-separated values.",
        "missing_terms": "Terms not found in any data source return an empty array in results. All requested terms always appear as keys.",
        "same_schema_as_single": "Each entry in results[term] has the same shape as entries in the /term-series series array.",
    },
}

REDDIT_GET_TOP_NGRAMS = {
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "array",
                                "description": "N-gram frequency entries sorted by count descending.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "types": {"type": "string", "description": "The n-gram string"},
                                        "counts": {"type": "integer", "description": "Total occurrence count over the date range"},
                                    },
                                },
                            },
                            "metadata": {
                                "type": "object",
                                "description": "Request metadata echoed back",
                                "properties": {
                                    "granularity": {"type": "string", "description": "Granularity used (daily/weekly/monthly)"},
                                    "entity": {"type": "string", "description": "Entity ID used"},
                                },
                            },
                        },
                    },
                    "example": {
                        "data": [
                            {"types": "the", "counts": 12345678},
                            {"types": "of", "counts": 9876543},
                        ],
                        "metadata": {"granularity": "daily", "entity": "AskReddit"},
                    },
                }
            },
        }
    }
}

REDDIT_TERM_SERIES = {
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "The n-gram term that was looked up (echoed back).",
                            },
                            "latest_available_date": {
                                "type": "string",
                                "format": "date",
                                "description": "Most recent date with data for this entity.",
                            },
                            "series": {
                                "type": "array",
                                "description": "Time series entries, one per date, sorted chronologically.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "date": {"type": "string", "format": "date"},
                                        "counts": {"type": "integer", "description": "Total count for this term on this date"},
                                        "rank": {"type": "integer", "description": "Rank by count on this date (1 = most frequent). 0 means not ranked."},
                                    },
                                },
                            },
                        },
                    },
                    "example": {
                        "type": "trump",
                        "latest_available_date": "2026-04-20",
                        "series": [
                            {"date": "2026-04-19", "counts": 41964, "rank": 487},
                            {"date": "2026-04-20", "counts": 45655, "rank": 455},
                        ],
                    },
                }
            },
        }
    },
}

STORYWRANGLER_ALLOTAXONOMETER = {
    "x-powered-by": "rust",
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "normalization": {"type": "number", "description": "Normalization constant for the rank-turbulence divergence"},
                            "delta_sum": {"type": "number", "description": "Sum of normalized divergence elements — the actual D_alpha^R value"},
                            "diamond_counts": {"type": "array", "description": "2D rank-space histogram used to render the diamond plot"},
                            "max_delta_loss": {"type": "number", "description": "Maximum delta-loss value (used for color-scale normalization)"},
                            "ncells": {"type": "integer", "description": "Number of cells along one side of the diamond grid; use to size the band scale"},
                            "maxlog10": {"type": "number", "description": "Largest log10(rank) across both systems, rounded up to at least 1; use to label diamond axes"},
                            "alpha": {"type": "number", "description": "Alpha parameter used in the computation"},
                            "balance": {"type": "number", "description": "Balance measure between the two systems (0.5 = equal, >0.5 = system 2 dominates)"},
                            "wordshift": {
                                "type": "array",
                                "description": "Top contributing types, sorted by absolute divergence contribution.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "description": "The n-gram / token"},
                                        "rank1": {"type": "integer", "description": "Rank in system 1 (0 = absent)"},
                                        "rank2": {"type": "integer", "description": "Rank in system 2 (0 = absent)"},
                                        "score": {"type": "number", "description": "Signed divergence contribution (positive = system 2 favours this type)"},
                                    },
                                },
                            },
                            "meta": {
                                "type": "object",
                                "description": "Request metadata echoed back",
                                "properties": {
                                    "system1": {"type": "object", "description": "System 1 parameters: entity, dates, filters, type count"},
                                    "system2": {"type": "object", "description": "System 2 parameters: entity, dates, filters, type count"},
                                    "domain": {"type": "string", "description": "Dataset domain"},
                                    "dataset": {"type": "string", "description": "Dataset ID"},
                                    "granularity": {"type": "string", "description": "Granularity used"},
                                },
                            },
                        },
                    },
                    "example": {
                        "normalization": 0.9871,
                        "diamond_counts": [[0, 1, 0], [2, 5, 3], [1, 4, 2]],
                        "max_delta_loss": 0.0421,
                        "alpha": 1.0,
                        "balance": 0.523,
                        "wordshift": [
                            {"type": "COVID", "rank1": 850, "rank2": 45, "score": 0.0189},
                            {"type": "election", "rank1": 1200, "rank2": 78, "score": 0.0142},
                            {"type": "the", "rank1": 1, "rank2": 2, "score": -0.0021},
                        ],
                        "meta": {
                            "system1": {
                                "entity": "wikidata:Q30",
                                "dates": "2024-10-01,2024-10-31",
                                "filters": {},
                                "types": 50000,
                            },
                            "system2": {
                                "entity": "wikidata:Q145",
                                "dates": "2024-11-01,2024-11-30",
                                "filters": {},
                                "types": 48000,
                            },
                            "domain": "wikimedia",
                            "dataset": "ngrams",
                            "granularity": "daily",
                        },
                    },
                }
            },
        }
    },
}

BABYNAMES_GET_BABYNAMES_TOP_NGRAMS = {
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "array",
                                "description": "Baby name frequency entries sorted by count descending.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "types": {"type": "string", "description": "The baby name"},
                                        "counts": {"type": "integer", "description": "Number of babies given this name in the date range"},
                                    },
                                },
                            },
                            "metadata": {
                                "type": "object",
                                "description": "Request metadata echoed back",
                                "properties": {
                                    "location": {"type": "string", "description": "Entity ID used"},
                                    "sex": {"type": "string", "description": "Sex filter applied (M, F, or null)"},
                                },
                            },
                        },
                    },
                    "example": {
                        "data": [
                            {"types": "James", "counts": 85234},
                            {"types": "John", "counts": 79102},
                            {"types": "Robert", "counts": 75680},
                        ],
                        "metadata": {"location": "wikidata:Q30", "sex": "M"},
                    },
                }
            },
        }
    }
}

ZONING_BYLAWS_GET_ZONING_BYLAWS_NGRAMS = {
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "array",
                                "description": "Top words in the town's zoning bylaw, sorted by frequency descending.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "types": {"type": "string", "description": "Word token"},
                                        "counts": {"type": "integer", "description": "Frequency count of the word"},
                                    },
                                },
                            },
                            "metadata": {
                                "type": "object",
                                "description": "Request metadata echoed back",
                                "properties": {
                                    "location": {"type": "string", "description": "Entity ID used"},
                                },
                            },
                        },
                    },
                    "example": {
                        "data": [
                            {"types": "the", "counts": 4394},
                            {"types": "of", "counts": 2559},
                            {"types": "and", "counts": 1956},
                        ],
                        "metadata": {"location": "Arlington"},
                    },
                }
            },
        }
    }
}
