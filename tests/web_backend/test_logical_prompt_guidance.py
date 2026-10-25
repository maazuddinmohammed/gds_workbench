"""Logical guidance retains the contract while clarifying generated endpoints."""

# Synthetic fixtures only; these checks do not prove provider modeling quality.
# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

import pytest
from gds_workbench_api.features.logical.policy import project_logical_audit_policy
from pydantic import JsonValue

from tests.web_backend.test_logical_candidate import _answer, _validator

SEED_ROOT = Path(__file__).resolve().parents[2] / "database/seed"
# Seed 05 v2 is a second version of the global defaults and must keep the same boundaries.
PROMPT_SETS = {
    "default": json.loads(
        (SEED_ROOT / "05_global_prompt_defaults.template.sql")
        .read_text()
        .split("$workflow_defaults$")[1]
    ),
    "v2": json.loads(
        (SEED_ROOT / "05_global_prompt_defaults.template.v2.sql")
        .read_text()
        .split("$workflow_defaults$")[1]
    ),
}


@pytest.mark.parametrize("prompt_set", sorted(PROMPT_SETS))
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_logical_defaults_describe_the_compact_answer_and_keep_boundaries(
    prompt_set: str, mode: str
) -> None:
    row = next(
        item
        for item in PROMPT_SETS[prompt_set]
        if item["project_workflow"] == "logical"
        and item["workflow_execution_mode"] == mode
    )
    # v1 keeps hard-wrapped lines; compare both versions as flowing text.
    system = " ".join(row["system_prompt"].split())
    instruction = row["instruction_prompt"]
    assert len(row["system_prompt"]) + len(instruction) < 17_000
    placeholders = re.findall(r"\{\{\s*(\w+)\s*\}\}", instruction)
    assert len(placeholders) == len(set(placeholders))
    assert "table_index" in placeholders
    assert not any("conceptual" in name or "submodel" in name for name in placeholders)
    assert "Submodel" not in system
    assert (
        system.index("Decide each Entity's grain")
        < system.index("Consolidate only compatible")
        < system.index("After normalization, revisit")
    )
    for invariant in (
        "Preserve disagreements between registered",
        "null means unvalidated",
        "Duplicate target",
        "SourceSystemID/source namespace",
        "one value per Attribute at that grain",
        "meaningful repeating children and multivalued facts",
        "composite join",
        "Cite a table by its id (t1)",
        "never list or source it",
        "never list them",
        "the backend references the parent's generated key",
        "Omit definition when its single source column's Project description",
        "Add note only when the value is not a straight copy",
        "its identity plus only what changes",
        "retire marks saved records inactive; nothing is deleted",
        "Omission is not deletion",
        "Locked records cannot change",
        "Enforcement on rejects",
        "enforcement off can return",
        "Attempts are not accumulated",
        "source_refs_truncated",
    ):
        assert invariant in system, invariant
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
        assert "Reuse complete inline or previously read evidence" in system
        assert "get_logical_submodels" not in system
        assert "get_logical_submodels" not in row["agent_tool_names"]
    else:
        assert "All selected evidence is inline; there are no readers" in system
        assert {
            "object_context",
            "object_attribute_context",
            "object_relationship_context",
        } <= set(placeholders)


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
        if change.dataset == "logical_attribute"
        and row["logical_entity_name"] == "Customer"
    ]
    keys = [row for row in rows if row["logical_attribute_is_surrogate_key"]]
    assert [
        (row["logical_attribute_name"], row["logical_attribute_ordinal_position"])
        for row in keys
    ] == [("CustomerID", 1)]
    relationship = next(
        row
        for change in projected
        for row in change.records
        if change.dataset == "logical_relationship"
    )
    assert relationship["to_logical_attribute_name"] == "CustomerID"
