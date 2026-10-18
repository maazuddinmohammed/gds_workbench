"""Modeling rules the web workflow prompts and Atlas both state.

The web prompts (`database/seed/05_global_prompt_defaults.template.sql` and the alternate
set in its `.v2.sql` sibling) and the Atlas references are written for different agents, so
their prose differs, but these rules must agree. Each row names the rule, the web workflows
and Atlas file that state it, and a pattern each side must keep. When a rule changes, change
both sides and this table.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "atlas/atlas-plugin"
SEEDS = {
    "default": (
        ROOT / "database/seed/05_global_prompt_defaults.template.sql",
        "$workflow_defaults$",
    ),
    "alternate": (
        ROOT / "database/seed/05_global_prompt_defaults.template.v2.sql",
        "$alternate_defaults$",
    ),
}


def _flat(text: str) -> str:
    """Prompts and references are hard-wrapped; compare with whitespace collapsed."""
    return " ".join(text.split())


def _web_prompts(seed: Path, payload_tag: str) -> dict[str, str]:
    prompts: dict[str, str] = {}
    for default in json.loads(seed.read_text(encoding="utf-8").split(payload_tag)[1]):
        parts = (
            default.get(key) or ""
            for key in ("system_prompt", "instruction_prompt", "tool_instruction_prompt")
        )
        workflow = default["project_workflow"]
        prompts[workflow] = _flat(" ".join([prompts.get(workflow, ""), *parts]))
    return prompts


WEB_SETS = {name: _web_prompts(*seed) for name, seed in SEEDS.items()}

ZONE_WORKFLOWS = ("analysis", "code_generation", "conceptual", "mapping", "validation")
# (rule, web workflows, web pattern, Atlas file, Atlas pattern)
SHARED_RULES = [
    (
        "GDS is the Global Data Store",
        ZONE_WORKFLOWS,
        r"GDS means \*{0,2}Global Data Store",
        "references/terminology.md",
        r"GDS means Global Data Store",
    ),
    (
        "zone meanings",
        ("analysis", "conceptual"),
        r"`source`: data in its originating system, before lake ingestion",
        "references/terminology.md",
        r"`source`: data in its originating system, before lake ingestion",
    ),
    (
        "null is unknown, not false or zero",
        ("analysis", "conceptual", "mapping", "metadata_enrichment_object"),
        r"`null` means (?:unspecified or )?unavailable; `false` and `0`",
        "references/project/enrichment.md",
        r"`null` means unknown, not false",
    ),
    (
        "Conceptual is never a Logical input",
        ("logical",),
        r"Conceptual records are not inputs",
        "references/working-method.md",
        r"Conceptual is a standalone deliverable\.\*\* Never use it as input",
    ),
    (
        "no invented row choice",
        ("mapping",),
        r"Do not invent latest-wins, DISTINCT",
        "references/project/mapping-documents.md",
        r"Do not assume latest-wins or add DISTINCT",
    ),
    (
        "missing Attribute rule is a typed NULL placeholder",
        ("code_generation",),
        r"`CAST\(NULL AS declared_type\)`",
        "references/code-generation/sql.md",
        r"`CAST\(NULL AS <target type>\) AS <target column>`",
    ),
    (
        "unsupported rowset is a typed zero-row projection",
        ("code_generation",),
        r"zero-row typed-NULL\s+projection",
        "references/code-generation/sql.md",
        r"typed zero-row projection",
    ),
    (
        "no added casts, defaults or deduplication",
        ("code_generation",),
        r"Never add TRY_CAST, defaults, deduplication",
        "references/code-generation/sql.md",
        r"Do not add DISTINCT, TRY_CAST, rounding, COALESCE, deduplication or defaults",
    ),
    (
        "final projection ends at SourceSystemID without SELECT *",
        ("code_generation",),
        r"explicit SELECT in the mapped output order through `SourceSystemID`",
        "references/code-generation/sql.md",
        r"exact mapped column order through `SourceSystemID`.*No final `SELECT \*`",
    ),
    (
        "framework-owned columns stay out of the SELECT",
        ("code_generation",),
        r"omit the own generated surrogate, nine framework audit fields and applicable",
        "references/code-generation/sql.md",
        r"omit the own generated surrogate, nine framework audit fields and applicable",
    ),
    (
        "degenerate dimensions stay on the fact",
        ("dimensional",),
        r"degenerate_dimension Attribute for a supported transaction identifier",
        "references/dimensional-build/design.md",
        r"transaction identifier with no independent descriptive context may remain a degenerate",
    ),
]


@pytest.mark.parametrize(
    ("rule", "workflows", "web_pattern", "atlas_file", "atlas_pattern"),
    SHARED_RULES,
    ids=[row[0] for row in SHARED_RULES],
)
def test_web_prompts_and_atlas_state_the_same_rule(
    rule: str, workflows: tuple[str, ...], web_pattern: str, atlas_file: str, atlas_pattern: str
) -> None:
    for name, web in WEB_SETS.items():
        for workflow in workflows:
            assert re.search(web_pattern, web[workflow], re.DOTALL), (rule, name, workflow)
    atlas = _flat((PLUGIN / atlas_file).read_text(encoding="utf-8"))
    assert re.search(atlas_pattern, atlas, re.DOTALL), (rule, atlas_file)


def test_zone_codes_match_on_both_sides() -> None:
    zones = ("source", "bronze", "silver", "gold")
    terminology = (PLUGIN / "references/terminology.md").read_text(encoding="utf-8")
    for name, web in WEB_SETS.items():
        for workflow in ZONE_WORKFLOWS:
            assert all(f"`{zone}`" in web[workflow] for zone in zones), (name, workflow)
    assert all(f"`{zone}`:" in terminology for zone in zones)
