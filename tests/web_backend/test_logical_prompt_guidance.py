"""Logical guidance retains the contract while clarifying generated endpoints."""

# Synthetic fixtures only; these checks do not prove provider modeling quality.
# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
from gds_workbench_api.features.logical.policy import project_logical_audit_policy
from pydantic import JsonValue

from tests.web_backend.test_logical_candidate import _candidate, _validator

DEFAULTS = json.loads(
    (Path(__file__).resolve().parents[2] / "database/seed/05_global_prompt_defaults.template.sql")
    .read_text()
    .split("$workflow_defaults$")[1]
)


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_logical_defaults_are_compact_and_keep_modeling_boundaries(mode: str) -> None:
    row = next(
        item
        for item in DEFAULTS
        if item["model_workflow"] == "logical" and item["workflow_execution_mode"] == mode
    )
    system = row["system_prompt"]
    instruction = row["instruction_prompt"]
    assert len(system) + len(instruction) < 17_000
    placeholders = re.findall(r"\{\{\s*(\w+)\s*\}\}", instruction)
    assert len(placeholders) == len(set(placeholders))
    assert not any("conceptual" in name for name in placeholders)
    assert (
        system.index("Plan coherent business Submodels first")
        < system.index("Decide each Entity's grain")
        < system.index("After normalization, revisit")
    )
    for invariant in (
        "Preserve disagreements between registered",
        "null means unvalidated",
        "Duplicate target",
        "calibrated confidence",
        "SourceSystemID/source namespace",
        "one value per Attribute at that grain",
        "meaningful repeating children and multivalued facts",
        "composite join",
        "Endpoint validation occurs before backend projection",
        "sources=[]",
        "Omission is not deletion",
        "all candidate lock flags are false",
        "Enforcement on rejects",
        "enforcement off can return",
        "Attempts are not accumulated",
        "source_refs_truncated",
    ):
        assert invariant in system
    assert "only at `high` confidence" not in system
    assert "Author a relationship only when both association" not in system
    if mode == "tool_assisted":
        assert "next_cursor/is_complete" in system
        assert "Reuse complete inline or previously read evidence" in system
    else:
        assert "All selected evidence is inline; there are no readers" in system
        assert {"object_context", "object_attribute_context", "object_relationship_context"} <= set(
            placeholders
        )


async def test_referenced_own_surrogate_must_be_explicit_before_policy_projection() -> None:
    candidate = cast(dict[str, Any], _candidate())
    candidate["attributes"][0]["logical_attribute_name"] = "SourceCustomerID"
    validator = _validator()
    projected = project_logical_audit_policy(
        changes=validator.parse_validated(cast(JsonValue, candidate)),
        applied=None,
        raw_template={"schema_version": "1.0", "columns": []},
    )
    own_key = next(
        row
        for change in projected
        if change.dataset == "logical_attribute"
        for row in change.records
        if row["logical_attribute_name"] == "CustomerID"
    )
    candidate["relationships"] = [
        {
            "logical_relationship_name": "SourceToGeneratedIdentity",
            "logical_relationship_definition": "One source identity maps to one generated identity.",
            "from_logical_entity_schema_name": "silver",
            "from_logical_entity_name": "Customer",
            "from_logical_attribute_name": "SourceCustomerID",
            "to_logical_entity_schema_name": "silver",
            "to_logical_entity_name": "Customer",
            "to_logical_attribute_name": "CustomerID",
            "logical_relationship_cardinality": "one_to_one",
            "logical_relationship_confidence": "medium",
            "logical_relationship_basis": "Synthetic fixture business identity.",
            "logical_relationship_cardinality_basis": "One generated identity per source record.",
            "logical_relationship_status": "active",
            "logical_relationship_is_locked": False,
        }
    ]
    omitted = await validator.validate(cast(JsonValue, candidate))
    assert {issue.code for issue in omitted.issues} == {"candidate.relationship_endpoint_missing"}
    candidate["attributes"].append(own_key)
    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()
    projected = project_logical_audit_policy(
        changes=validator.parse_validated(cast(JsonValue, candidate)),
        applied=None,
        raw_template={"schema_version": "1.0", "columns": []},
    )
    assert (
        sum(
            row["logical_attribute_name"] == "CustomerID"
            for change in projected
            if change.dataset == "logical_attribute"
            for row in change.records
        )
        == 1
    )
    description = validator.output_schema()["description"]
    assert isinstance(description, str)
    assert "Endpoint validation precedes backend projection" in description
    assert "Legacy selected_metadata" in description
    assert "under enrichment" in description
