from __future__ import annotations

import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = REPOSITORY_ROOT / "plugins" / "v2" / "gds"


def word_count(path: Path) -> int:
    return len(re.findall(r"\S+", path.read_text()))


def test_static_instruction_footprint_proxy_stays_bounded() -> None:
    """Guard file footprint, not actual model-token usage."""
    v2_skills = sorted((V2_ROOT / "skills").glob("*/SKILL.md"))
    v2_markdown = sorted((V2_ROOT / "skills").rglob("*.md"))

    assert len(v2_skills) == 1

    v2_router_words = word_count(v2_skills[0])
    v2_markdown_words = sum(map(word_count, v2_markdown))

    assert v2_router_words <= 600
    assert max(map(word_count, v2_markdown)) <= 700
    assert v2_markdown_words <= 5_500


def test_router_requires_progressive_reference_loading() -> None:
    router = (V2_ROOT / "skills" / "gds" / "SKILL.md").read_text()

    assert "Load only the reference for the active target" in router
    assert "Do not preload every workflow" in router
    assert "Do not load an entire Snapshot into model context" in router
    assert "run `readiness` once for a known target" in router
    assert "never precede it with `inspect`" in router

    session = (V2_ROOT / "skills" / "gds" / "references" / "session.md").read_text()
    helper = (V2_ROOT / "skills" / "gds" / "references" / "local-helper.md").read_text()
    assert (
        "run `readiness` for a known target or `inspect` otherwise—never both"
        in session
    )
    assert "never call both as setup" in helper
