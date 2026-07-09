"""Section matching for get-documentation — pure functions, no I/O.

Mirrors the scrolly-kit MCP matching order: exact slug, exact title
(case-insensitive), then fuzzy substring against slug, title, and
use_cases keywords.
"""
from __future__ import annotations

from typing import Optional, TypedDict


class Section(TypedDict):
    title: str
    slug: str
    use_cases: str


def match_section(query: str, sections: list[Section]) -> Optional[Section]:
    """Return the best-matching section for *query*, or None."""
    q = query.strip()
    ql = q.lower()

    for s in sections:
        if s["slug"] == q:
            return s
    for s in sections:
        if s["title"].lower() == ql:
            return s
    for s in sections:
        if ql in s["slug"].lower() or ql in s["title"].lower():
            return s
    for s in sections:
        if ql in s.get("use_cases", "").lower():
            return s
    return None


def suggest_sections(query: str, sections: list[Section], limit: int = 5) -> list[Section]:
    """Loose word-overlap suggestions for a failed match."""
    words = {w for w in query.lower().split() if len(w) > 2}
    if not words:
        return sections[:limit]
    scored = []
    for s in sections:
        haystack = f"{s['slug']} {s['title']} {s.get('use_cases', '')}".lower()
        score = sum(1 for w in words if w in haystack)
        if score:
            scored.append((score, s))
    scored.sort(key=lambda pair: -pair[0])
    return [s for _, s in scored[:limit]] or sections[:limit]
