from __future__ import annotations

import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = REPOSITORY_ROOT / "plugins" / "v2" / "gds"


def word_count(path: Path) -> int:
    return len(re.findall(r"\S+", path.read_text()))


def test_static_instruction_footprint_proxy_stays_bounded() -> None:
    """Guard the lazy-loaded instruction path, not every alternative guide at once."""
    v2_skills = sorted((V2_ROOT / "skills").glob("*/SKILL.md"))
    v2_markdown = sorted((V2_ROOT / "skills").rglob("*.md"))

    assert len(v2_skills) == 1

    v2_router_words = word_count(v2_skills[0])
    v2_markdown_words = sum(map(word_count, v2_markdown))
    logical_path = [
        v2_skills[0],
        V2_ROOT / "skills/gds/references/session.md",
        V2_ROOT / "skills/gds/references/workflow-targets.md",
        V2_ROOT / "skills/gds/references/change-sets.md",
        V2_ROOT / "skills/gds/references/local-helper.md",
        V2_ROOT / "skills/gds/references/server-handoff.md",
        V2_ROOT / "skills/gds/references/staging.md",
        V2_ROOT / "skills/gds/references/workflows/logical-build.md",
        V2_ROOT / "skills/gds/references/workflows/model-input-scope.md",
        V2_ROOT / "skills/gds/references/workflows/profiling.md",
        V2_ROOT / "skills/gds/references/workflows/analysis.md",
        V2_ROOT / "skills/gds/references/workflows/conceptual.md",
        V2_ROOT / "skills/gds/references/workflows/assertions.md",
    ]

    assert v2_router_words <= 600
    assert max(map(word_count, v2_markdown)) <= 700
    assert v2_markdown_words <= 6_500
    assert sum(map(word_count, logical_path)) <= 3_700


def test_router_requires_progressive_reference_loading() -> None:
    router = (V2_ROOT / "skills" / "gds" / "SKILL.md").read_text()

    assert "only the active guide" in router
    assert "never load a complete Snapshot into context" in router
    assert "Run local `readiness` once for a known target" in router
    assert "local helper's `inspect` command" in router

    session = (V2_ROOT / "skills" / "gds" / "references" / "session.md").read_text()
    helper = (V2_ROOT / "skills" / "gds" / "references" / "local-helper.md").read_text()
    assert "On resume call local `status`" in session
    assert "bounded `select`" in helper
