"""OpenAPI response documentation for domain routers.

Static `openapi_extra` payloads — response schemas, examples, and
frontend/performance notes — kept out of the routers so endpoint logic
stays readable. Constants are named <ROUTER>_<ENDPOINT_FUNCTION>.
"""

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

STORYWRANGLER_TOP_NGRAMS = {
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
                                "description": "Type/count entries sorted by count descending. With dates2, replaced by two arrays keyed by each date range (e.g. '2024-10-01_2024-10-07').",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "types": {"type": "string", "description": "The type (n-gram, name, ...)"},
                                        "counts": {"type": "number", "description": "Total count over the date range under the selected weight. Matches the declared column type: integer for integer-counted datasets (wikimedia, bluesky, twitter), float for weighted measures (reddit)."},
                                    },
                                },
                            },
                            "metadata": {
                                "type": "object",
                                "description": "Request metadata echoed back",
                                "properties": {
                                    "domain": {"type": "string", "description": "Dataset domain"},
                                    "dataset": {"type": "string", "description": "Dataset ID"},
                                    "dataset_version": {"type": "string", "description": "Registered dataset version served"},
                                    "entity": {"type": "string", "description": "Entity ID used (null for entity-less datasets)"},
                                    "filters": {"type": "object", "description": "Filter dimensions applied, defaults included"},
                                    "weight": {"type": "string", "description": "Count column used"},
                                },
                            },
                        },
                    },
                    "example": {
                        "data": [
                            {"types": "the", "counts": 12345678},
                            {"types": "of", "counts": 9876543},
                        ],
                        "metadata": {
                            "domain": "wikimedia",
                            "dataset": "ngrams",
                            "dataset_version": "1.0.0",
                            "entity": "wikidata:Q30",
                            "filters": {"ngram_size": 1, "granularity": "daily"},
                            "weight": "pv_count",
                        },
                    },
                }
            },
        }
    },
    "x-frontend-notes": {
        "filters": "Filter dimensions are dataset-specific query params using registered column names (?ngram_size=1&granularity=daily for wikimedia, ?n=1&lang=en for reddit, ?sex=M for babynames). Discover them via GET /registry/{domain}/{dataset_id} (level_order / transform.filter_dimensions).",
        "comparison": "Pass dates2 for a two-system temporal comparison; the response keys the two arrays by their date ranges instead of 'data'. mongodb pass-through datasets (twitter) accept single dates only.",
        "dates_range": "A range entirely outside the slice's availability is a 400 naming the actual bounds (from manifest.availability) — no need to look them up before querying.",
    },
}

STORYWRANGLER_TERM_SERIES = {
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "description": "The type/term looked up (echoed back)."},
                            "latest_available_date": {"type": "string", "format": "date", "description": "Most recent date with data for the resolved slice."},
                            "series": {
                                "type": "array",
                                "description": "One entry per date, chronological. `rank`/`freq` appear only when the dataset declares rank_column/freq_column. With `?include=`, each entry also carries a key named for the requested provenance role (e.g. `articles`) holding a ranked `[[document, score], ...]` list.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "date": {"type": "string", "format": "date"},
                                        "counts": {"type": "integer", "description": "The selected measure for this type on this date."},
                                        "rank": {"type": "integer", "description": "Rank under the chosen measure (omitted when undeclared)."},
                                        "freq": {"type": "number", "description": "Normalized frequency (omitted when undeclared)."},
                                    },
                                },
                            },
                        },
                    },
                    "example": {
                        "type": "trump",
                        "latest_available_date": "2026-01-04",
                        "series": [
                            {"date": "2025-12-05", "counts": 5352, "rank": 811, "freq": 0.000117},
                            {"date": "2025-12-06", "counts": 4332, "rank": 847, "freq": 0.000112},
                        ],
                    },
                }
            },
        }
    },
    "x-performance": {
        "fast_path": "Types in the sparkline vocabulary are a hash-bucket point lookup on the type-first companion (~tens of ms).",
        "slow_fallback": "Types outside it fall back to a scan of the date-first tree, bounded to the requested range and directory-pruned; an undated request is clamped to the slice availability, so the scan is never an open walk of the whole tree. A dataset that is itself type-first (orientation:type-first, e.g. a term-bucketed tree) has no slow path: every request is a bucket point lookup and a miss is an empty series.",
        "mixed_batch": "Batch requests scan only the types the sparkline missed: vocabulary types return fast regardless, out-of-vocabulary types add one scan for just those.",
        "mongodb": "Pass-through datasets (twitter) serve the range as a plain find + time filter + sort — a range read, not an aggregation.",
        "include": "?include= adds one bucket-routed read per provenance companion; omit it for the tidy counts/rank/freq series. include_dates= narrows the documents to specific dates (e.g. the two comparison dates a UI actually renders) without touching the series range.",
    },
    "x-frontend-notes": {
        "dataset": "Selected by ?domain=&dataset= (the caller-facing types-counts dataset). The type-first sparkline fast path is resolved automatically from lineage.derived_from + orientation:type-first — no param needed. ?sparkline_dataset= remains as a deprecated override. Filter dims (?n=&lang=, ?ngram_size=&granularity=) use the dataset's registered column names.",
        "include": "?include=<role> (or include=all) attaches a type-documents companion's ranked source documents per date, nested under a key named for the role (e.g. 'articles': [[url, score], ...]). Roles are declared on the companion and resolved via lineage; a raw companion dataset id also works (deprecated).",
        "formats": "Works across parquet_hive, flat parquet, and mongodb pass-through (per-term range reads). rank/freq are present only when the dataset registers rank_column/freq_column; otherwise the series is counts-only.",
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


STORYWRANGLER_WORDSHIFT = {
    "x-powered-by": "rust",
    "x-frontend-notes": (
        "Filters are off by default. The conventional labMT neutral lens is "
        "applied client-side by passing stop_lens=4,6 — the endpoint does not "
        "bake in a default so callers stay in control. meta.stop_lens / "
        "meta.stop_words echo whatever was applied, for reproducible captions."
    ),
    "responses": {
        "200": {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "entries": {
                                "type": "array",
                                "description": "Per-word contributions, sorted by absolute shift score descending. Truncated to wordshift_limit; component sums are always over the full vocabulary.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "description": "The word (labMT-scored type)"},
                                        "p_diff": {"type": "number", "description": "Change in relative frequency, p_2 - p_1 (over the surviving scored vocabulary)"},
                                        "s_diff": {"type": "number", "description": "Change in score, s_2 - s_1 — always 0 for a single lexicon"},
                                        "p_avg": {"type": "number", "description": "Mean relative frequency, 0.5 * (p_1 + p_2)"},
                                        "s_ref_diff": {"type": "number", "description": "Deviation of the word's score from the reference, s - s_ref"},
                                        "shift_score": {"type": "number", "description": "Normalized signed contribution (positive = pushed system 2's average sentiment up)"},
                                    },
                                },
                            },
                            "component_sums": {
                                "type": "object",
                                "description": "Cumulative sign-quadrant contributions for the stacked total bars (Shifterator's component sums, normalized). pos_s/neg_s carry the s_diff term and are 0 for a single lexicon.",
                                "properties": {
                                    "pos_s_pos_p": {"type": "number"},
                                    "pos_s_neg_p": {"type": "number"},
                                    "neg_s_pos_p": {"type": "number"},
                                    "neg_s_neg_p": {"type": "number"},
                                    "pos_s": {"type": "number"},
                                    "neg_s": {"type": "number"},
                                },
                            },
                            "total_diff": {"type": "number", "description": "Unnormalized sum of raw shift scores (s_avg_2 - s_avg_1)"},
                            "norm": {"type": "number", "description": "Normalization denominator (Σ|shift|) applied to all scores"},
                            "s_avg_1": {"type": "number", "description": "Frequency-weighted mean labMT score of system 1 (Φ_avg)"},
                            "s_avg_2": {"type": "number", "description": "Frequency-weighted mean labMT score of system 2"},
                            "reference_value": {"type": "number", "description": "Reference score partitioning positive/negative regimes (system 1's weighted mean unless overridden)"},
                            "normalization": {"type": "string", "description": "Normalization scheme; always 'variation'"},
                            "meta": {
                                "type": "object",
                                "description": "Request metadata echoed back",
                                "properties": {
                                    "system1": {"type": "object", "description": "System 1 parameters: entity, dates, filters, type count"},
                                    "system2": {"type": "object", "description": "System 2 parameters: entity, dates, filters, type count"},
                                    "lexicon": {"type": "string", "description": "labMT language lexicon used to score both systems"},
                                    "weight": {"type": "string", "description": "Count column used"},
                                    "stop_lens": {"type": "array", "nullable": True, "description": "Neutral-word lens applied as [lo, hi], or null. Words scored inside [lo, hi] were dropped before computing the shift.", "items": {"type": "number"}},
                                    "stop_words": {"type": "array", "nullable": True, "description": "Words excluded from the shift (sorted), or null.", "items": {"type": "string"}},
                                    "domain": {"type": "string", "description": "Dataset domain"},
                                    "dataset": {"type": "string", "description": "Dataset ID"},
                                    "dataset_version": {"type": "string", "description": "Registered dataset version served"},
                                    "wordshift_version": {"type": "string", "description": "wordshift package version that computed the shift"},
                                },
                            },
                        },
                    },
                    "example": {
                        "entries": [
                            {"type": "happy", "p_diff": 0.00042, "s_diff": 0.0, "p_avg": 0.0011, "s_ref_diff": 3.32, "shift_score": 0.0184},
                            {"type": "crisis", "p_diff": -0.00031, "s_diff": 0.0, "p_avg": 0.0008, "s_ref_diff": -2.67, "shift_score": 0.0121},
                        ],
                        "component_sums": {
                            "pos_s_pos_p": 0.31, "pos_s_neg_p": -0.12,
                            "neg_s_pos_p": -0.09, "neg_s_neg_p": 0.24,
                            "pos_s": 0.0, "neg_s": 0.0,
                        },
                        "total_diff": 0.043,
                        "norm": 1.87,
                        "s_avg_1": 5.42,
                        "s_avg_2": 5.46,
                        "reference_value": 5.42,
                        "normalization": "variation",
                        "meta": {
                            "system1": {"entity": "Australia", "dates": "2026-07-18", "filters": {"ngram_size": 1, "granularity": "daily"}, "types": 4540},
                            "system2": {"entity": "Canada", "dates": "2026-07-18", "filters": {"ngram_size": 1, "granularity": "daily"}, "types": 4531},
                            "lexicon": "labMT_English",
                            "weight": "count",
                            "stop_lens": [4.0, 6.0],
                            "stop_words": None,
                            "domain": "wikimedia",
                            "dataset": "ngrams",
                            "dataset_version": "1.0.0",
                            "wordshift_version": "0.1.1",
                        },
                    },
                }
            },
        }
    },
}
