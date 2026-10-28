"""Logical guidance retains the contract while clarifying generated endpoints."""

# Synthetic fixtures only; these checks do not prove provider modeling quality.
# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

import pytest
from pydantic import JsonValue
from tests.web_backend.test_logical_candidate import _answer, _validator

from gds_workbench_api.features.logical.policy import project_logical_audit_policy

SEED_ROOT = Path(__file__).resolve().parents[2] / "database/seed"
PROMPTS = json.loads(
    (SEED_ROOT / "05_global_prompt_defaults.template.sql")
    .read_text()
    .split("$workflow_defaults$")[1]
)


# Boundaries both stages keep: the compact answer, backend-owned keys and safe repair.
SHARED_RULES = (
    "SourceSystemID/source namespace",
    "composite join",
    "never list or source it",
    "never list them",
    "the backend references the parent's generated key",
    "Omit definition when its single source column's Project description",
    "Add note only when the value is not a straight copy",
    "its identity plus only what changes",
    "retire marks saved records inactive; nothing is deleted",
    "Omission is not deletion",
    "Locked records cannot change",
    "Attempts are not accumulated",
)
# A Build call models one Subject Area against the model so far and owns its coverage.
BUILD_RULES = (
    "Preserve disagreements between registered",
    "null means unvalidated",
    "Duplicate target",
    "one value per Attribute at that grain",
    "meaningful repeating children and multivalued facts",
    "Cite a table by its id (t1)",
    "never cite it as a source",
    "Enforcement on rejects",
    "enforcement off can return",
    "source_refs_truncated",
)
STAGE_INPUTS = {
    "build_authoring": {
        "subject_area_context",
        "table_index",
        "existing_entities",
        "neighbor_entities",
        "entity_directory",
        "coverage_threshold_percent",
    },
    "optimize_authoring": {
        "table_index",
        "model_summary",
        "unlinked_analysis_edges",
        "type_conflicts",
        "name_variants",
        "entity_details",
    },
}


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("stage", sorted(STAGE_INPUTS))
def test_logical_defaults_describe_the_compact_answer_and_keep_boundaries(
    mode: str, stage: str
) -> None:
    row = next(
        item
        for item in PROMPTS
        if item["project_workflow"] == "logical"
        and item["workflow_execution_mode"] == mode
        and item["workflow_stage_code"] == stage
    )
    # Prompts keep hard-wrapped lines; compare them as flowing text.
    system = " ".join(row["system_prompt"].split())
    instruction = row["instruction_prompt"]
    assert len(row["system_prompt"]) + len(instruction) < 17_000
    placeholders = re.findall(r"\{\{\s*(\w+)\s*\}\}", instruction)
    assert len(placeholders) == len(set(placeholders))
    # Each stage reads only its own input set; Optimize has no area and no coverage.
    other = next(name for name in STAGE_INPUTS if name != stage)
    assert STAGE_INPUTS[stage] <= set(placeholders)
    assert not (STAGE_INPUTS[other] - STAGE_INPUTS[stage]) & set(placeholders)
    assert not any("submodel" in name for name in placeholders)
    assert "Submodel" not in system
    for invariant in SHARED_RULES:
        assert invariant in system, invariant
    for invariant in BUILD_RULES:
        assert (invariant in system) == (stage == "build_authoring"), invariant
    if stage == "build_authoring":
        assert (
            system.index("Reuse before you create")
            < system.index("Decide each new or changed Entity's grain")
            < system.index("Consolidate only compatible")
            < system.index("After normalization, revisit")
        )
    else:
        assert (
            system.index("Cross-area links")
            < system.index("Duplicates:")
            < system.index("Type conflicts:")
        )
    # Rules the backend now applies are no longer the agent's job.
    for removed in (
        "logical_attribute_is_surrogate_key",
        "ordinal",
        "lock flags are false",
        "Endpoint validation occurs before backend projection",
        "logical_relationship_cardinality_basis",
        "dependency order is 0",
    ):
        assert removed not in system, removed
    if mode == "tool_assisted":
        assert "next_cursor/is_complete" in system
        # Only the whole-model readers remain: no list_* or Submodel readers.
        assert {name for name in row["agent_tool_names"] if name.startswith("get_logical_")} == {
            "get_logical_entities",
            "get_logical_attributes",
            "get_logical_relationships",
        }
        assert not any(
            "submodel" in name or name.startswith("list_") for name in row["agent_tool_names"]
        )
    else:
        assert row["agent_tool_names"] is None
        assert "there are no readers" in system
        assert (
            {"object_context", "object_attribute_context", "object_relationship_context"}
            <= set(placeholders)
        ) == (stage == "build_authoring")


def test_generated_parent_key_is_projected_once() -> None:
    # The answer names the parent Entity only; the backend adds and references its key.
    validator = _validator()
    projected = project_logical_audit_policy(
        changes=validator.parse_validated(cast(JsonValue, _answer())),
        applied=None,
        raw_template={"schema_version": "1.0", "columns": []},
    )
    rows = [
        row
        for change in projected
        for row in change.records
        if change.dataset == "logical_attribute" and row["logical_entity_name"] == "Customer"
    ]
    keys = [row for row in rows if row["logical_attribute_is_surrogate_key"]]
    assert [
        (row["logical_attribute_name"], row["logical_attribute_ordinal_position"]) for row in keys
    ] == [("CustomerID", 1)]
    relationship = next(
        row
        for change in projected
        for row in change.records
        if change.dataset == "logical_relationship"
    )
    assert relationship["to_logical_attribute_name"] == "CustomerID"
