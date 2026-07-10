#!/usr/bin/env python3
"""Sync canonical agent assets to their distribution copies.

Canonical source:  .claude/skills/  (edit skills there, and only there)
Distribution copies (generated — do not edit):
  packages/sdk/src/storywrangler/agent_assets/skills/  → shipped in the SDK
      wheel; `storywrangler new` scaffolds them into new dataset projects.
  plugins/storywrangler/skills/                        → the Claude plugin
      installed via the in-repo marketplace.
  frontend/src/lib/skills/<skill>.md                   → rendered on the docs
      site's /llms page (Agents & MCP) so the skill content is viewable/copyable.

SKILL.md only — evals/ stay in the canonical location (dev-side, not shipped).
Run after editing a skill: uv run python scripts/sync_agent_assets.py
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / ".claude" / "skills"
SKILLS = ["storywrangler-analyst", "storywrangler-submission"]
TARGETS = [
    ROOT / "packages" / "sdk" / "src" / "storywrangler" / "agent_assets" / "skills",
    ROOT / "plugins" / "storywrangler" / "skills",
]


def main() -> int:
    missing = [s for s in SKILLS if not (CANONICAL / s / "SKILL.md").exists()]
    if missing:
        print(f"canonical skill(s) missing: {missing}", file=sys.stderr)
        return 1
    for target_root in TARGETS:
        for skill in SKILLS:
            dst = target_root / skill / "SKILL.md"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(CANONICAL / skill / "SKILL.md", dst)
            print(f"synced {dst.relative_to(ROOT)}")

    # Frontend copy is flat (<skill>.md) so the docs site can glob-import it.
    frontend_skills = ROOT / "frontend" / "src" / "lib" / "skills"
    frontend_skills.mkdir(parents=True, exist_ok=True)
    for skill in SKILLS:
        dst = frontend_skills / f"{skill}.md"
        shutil.copy2(CANONICAL / skill / "SKILL.md", dst)
        print(f"synced {dst.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
