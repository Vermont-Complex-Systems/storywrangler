"""Tests for section matching — exact, title, substring, use_cases, suggestions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from storywrangler_mcp.matching import match_section, suggest_sections

SECTIONS = [
    {"title": "Getting started", "slug": "getting-started", "use_cases": "setup, first request, SDK install"},
    {"title": "Querying datasets", "slug": "querying", "use_cases": "filters, entities, term series, performance"},
    {"title": "Registering a dataset", "slug": "register", "use_cases": "submission, DatasetCreate, hive partitioning"},
    {"title": "API reference: wikimedia", "slug": "api-reference/wikimedia", "use_cases": "top ngrams, term series"},
    {"title": "scisciDB pipeline", "slug": "case-studies/scisciDB", "use_cases": "time-series endpoint, group_by"},
]


def test_exact_slug():
    assert match_section("register", SECTIONS)["slug"] == "register"


def test_exact_slug_beats_substring():
    # "querying" is a substring of nothing else — but "register" is a prefix of
    # "Registering a dataset"; exact slug must win before substring scanning.
    assert match_section("querying", SECTIONS)["slug"] == "querying"


def test_title_case_insensitive():
    assert match_section("getting STARTED", SECTIONS)["slug"] == "getting-started"


def test_substring_on_slug():
    assert match_section("wikimedia", SECTIONS)["slug"] == "api-reference/wikimedia"


def test_use_cases_keyword():
    assert match_section("hive partitioning", SECTIONS)["slug"] == "register"


def test_nested_slug():
    assert match_section("case-studies/scisciDB", SECTIONS)["slug"] == "case-studies/scisciDB"


def test_no_match_returns_none():
    assert match_section("kubernetes", SECTIONS) is None


def test_suggestions_rank_by_overlap():
    suggestions = suggest_sections("term series performance", SECTIONS)
    assert suggestions[0]["slug"] == "querying"


def test_suggestions_fall_back_to_head():
    suggestions = suggest_sections("zzz", SECTIONS, limit=2)
    assert len(suggestions) == 2
