"""Installed enrichment seeds render workflow-local inputs through physical completion."""

from __future__ import annotations

import re
from typing import Any

import pytest
from gds_workbench_api.features.workflows.authoring import stage_runner
from gds_workbench_api.features.workflows.authoring.context_contracts import workflow_input_contracts
from jsonschema import Draft202012Validator

from tests.mcp.conftest import bootstrap_postgres_database as bootstrap_postgres_database
from tests.mcp.test_database_metadata_enrichment_executor import (
    enrichment_seeded_actor as enrichment_seeded_actor,
)
from tests.mcp.test_database_metadata_enrichment_executor import (
    test_shared_executor_completes_physical_enrichment as execute_seeded_enrichment,
)
from tests.mcp.test_database_notebook_workflows import notebook_actor as notebook_actor


@pytest.mark.asyncio
@pytest.mark.parametrize("behavior", ["normal", "regenerate_attributes"])
async def test_installed_metadata_seed_inputs_reach_real_stage_and_physical_completion(
    enrichment_seeded_actor: Any, monkeypatch: pytest.MonkeyPatch, behavior: str
) -> None:
    # Exercise the governed create/start/claim, frozen plan, renderer and completion.
    # Inspect fixture evidence in memory; never log rendered prompts or physical data.
    original = stage_runner.render_prompt
    seen: list[tuple[str, tuple[str, ...]]] = []
    object_evidence: dict[tuple[str, ...], Any] = {}
    boundary_errors: list[tuple[str, int]] = []

    def inspect_render(**kwargs: Any) -> Any:
        definitions = {value.name: value for value in kwargs["variables"]}
        key = definitions["object_context"].resolver_key
        workflow = key.split(".")[1]
        assert workflow in {"metadata_enrichment_object", "metadata_enrichment_attribute"}
        contracts = workflow_input_contracts(workflow)
        assert set(definitions) == set(contracts)
        values = kwargs["resolver_values"]
        inputs: dict[str, Any] = {}
        for name, spec in contracts.items():
            definition = definitions[name]
            assert definition.resolver_key == (
                f"workflow.{workflow}.common.candidate_authoring.inputs.{name}"
            )
            assert not definition.is_required
            inputs[name] = values[definition.resolver_key]
            assert Draft202012Validator(spec["schema"]).is_valid(inputs[name])  # pyright: ignore[reportUnknownMemberType]
            assert re.search(r"\{\{\s*" + re.escape(name) + r"\s*\}\}", kwargs["templates"].instruction)
        assert len(inputs["object_context"]) == 1
        assert len(inputs["object_attribute_context"]) == 1
        object_row = inputs["object_context"][0]
        attribute_row = inputs["object_attribute_context"][0]
        key_fields = ("tenant_code", "system_code", "connection_code", "object_schema", "object_name")
        object_key = tuple(object_row[field] for field in key_fields)
        assert object_key == tuple(attribute_row[field] for field in key_fields)
        if workflow == "metadata_enrichment_object":
            object_evidence[object_key] = object_row
        elif behavior == "normal":
            assert object_evidence[object_key] == object_row
        if behavior == "regenerate_attributes":
            assert workflow == "metadata_enrichment_attribute"
            assert len(attribute_row["selected_attribute_names"]) == 31
            assert len(attribute_row["attributes"]) >= 31
        result = original(**kwargs)
        assert not result.unknown_placeholders and not result.warning_codes
        seen.append((workflow, object_key))
        return result

    def checked_render(**kwargs: Any) -> Any:
        try:
            return inspect_render(**kwargs)
        except Exception as error:
            frame = error.__traceback__
            while frame is not None and frame.tb_next is not None:
                frame = frame.tb_next
            boundary_errors.append((type(error).__name__, frame.tb_lineno if frame else 0))
            raise

    monkeypatch.setattr(stage_runner, "render_prompt", checked_render)
    try:
        await execute_seeded_enrichment(enrichment_seeded_actor, behavior)
    finally:
        assert not boundary_errors, boundary_errors
    if behavior == "normal":
        assert {workflow for workflow, _ in seen} == {
            "metadata_enrichment_object", "metadata_enrichment_attribute"
        }
        assert len(seen) == len(set(seen))
    else:
        assert len(seen) == 1
