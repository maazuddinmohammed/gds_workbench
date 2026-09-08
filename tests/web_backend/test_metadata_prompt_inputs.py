"""Metadata Prompt inputs, typed documentation and legacy rendering boundaries."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.metadata_enrichment.service import DescriptionValidator
from gds_workbench_api.features.prompts.contracts import PromptStageVariable
from gds_workbench_api.features.prompts.service import DatabasePromptService, PromptDatabase
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.plan import AgentRunPlan
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    PromptInputContract,
    get_prompt_input_contract,
    project_prompt_input_values,
)
from gds_workbench_api.features.workflows.authoring.repair import AgentContextPolicy
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
    render_prompt,
)
from jsonschema import Draft202012Validator
from pydantic import JsonValue

from tests.web_backend.test_agent_stage_runner import (
    _plan as base_plan,  # pyright: ignore[reportPrivateUsage]
)
from tests.web_backend.test_prompts import (
    PRINCIPAL,
    StageCatalogDatabase,
    StageCatalogTransaction,
    TemplateDetailDatabase,
    TemplateDetailTransaction,
)

PREFIX = "workflow.metadata_enrichment.one_shot.candidate_authoring"
LEGACY = f"{PREFIX}.context"
REFS = f"{PREFIX}.inputs.assigned_description_refs"
REQUESTS = f"{PREFIX}.inputs.description_requests"


def request_rows() -> list[dict[str, JsonValue]]:
    return [
        {
            "target_ref": "object:101",
            "kind": "object",
            "name": "orders",
            "schema": "bronze",
            "system": "CRM",
            "attributes": [
                {
                    "name": "order_id",
                    "storage_type": "STRING",
                    "inferred_type": "BIGINT",
                    "description": None,
                }
            ],
        },
        {
            "target_ref": "attribute:201",
            "kind": "attribute",
            "name": "order_id",
            "object_name": "orders",
            "object_description": None,
            "system": "CRM",
            "storage_type": "STRING",
            "inferred_type": "BIGINT",
            "type_evidence_method": "source_schema",
            "source_attribute": "OrderID",
            "source_description": "Source identifier.\nRetained across reloads.\t",
            "source_object_description": None,
        },
    ]


def plan(
    *, names: tuple[str, ...] = ("assigned_description_refs", "description_requests")
) -> AgentRunPlan:
    variables = (
        PromptVariableDefinition(
            name="stage_context", resolver_key=LEGACY, data_type="json", is_required=True
        ),
        *(
            PromptVariableDefinition(
                name=name,
                resolver_key=f"{PREFIX}.inputs.{name}",
                data_type="json",
                is_required=False,
            )
            for name in names
        ),
    )
    original = base_plan()
    stage = original.stages[0].model_copy(
        update={
            "templates": PromptComponentTemplates(
                system="Describe only requested metadata.",
                instruction=(
                    "Refs {{assigned_description_refs}}. "
                    "Requests {{description_requests}}. {{stage_context}}"
                ),
            ),
            "variables": variables,
        }
    )
    return original.model_copy(
        update={
            "model_workflow": "metadata_enrichment",
            "workflow_execution_mode": "one_shot",
            "stages": (stage,),
        }
    )


def contract(name: str) -> PromptInputContract:
    result = get_prompt_input_contract(
        model_workflow="metadata_enrichment",
        workflow_execution_mode="one_shot",
        stage_code="candidate_authoring",
        resolver_key=f"{PREFIX}.inputs.{name}",
    )
    assert result is not None
    return result


def project(
    context: JsonValue,
    *,
    selected_plan: AgentRunPlan | None = None,
    legacy: Mapping[str, object] | None = None,
) -> dict[str, object]:
    current = selected_plan or plan()
    return project_prompt_input_values(
        plan=current,
        stage=current.stages[0],
        context=context,
        resolver_values=legacy
        if legacy is not None
        else {LEGACY: context, "workflow.validation_failures": []},
    )


@pytest.mark.parametrize("name", ["assigned_description_refs", "description_requests"])
def test_named_contract_has_valid_schema_example_and_honest_availability(name: str) -> None:
    descriptor = contract(name)
    assert descriptor is not None
    assert descriptor.name == name
    assert descriptor.resolver_key == f"{PREFIX}.inputs.{name}"
    assert descriptor.data_type == "json"
    assert descriptor.source and descriptor.availability
    assert "25" in descriptor.availability
    assert descriptor.delivery == (
        "inline_value" if name == "assigned_description_refs" else "structured_context"
    )
    assert descriptor.context_path == (
        None
        if name == "assigned_description_refs"
        else "context.original_context.description_requests"
    )
    Draft202012Validator.check_schema(descriptor.value_schema)
    assert not list(
        Draft202012Validator(descriptor.value_schema).iter_errors(  # pyright: ignore[reportUnknownMemberType]
            descriptor.example
        )
    )


def test_description_schema_is_exact_current_request_union_and_bounds() -> None:
    descriptor = contract("description_requests")
    schema = descriptor.value_schema
    assert schema["type"] == "array"
    assert schema["minItems"] == 1 and schema["maxItems"] == 25
    validate = Draft202012Validator(schema).is_valid  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert validate(request_rows())
    rows = request_rows()
    rows[1].update(
        inferred_type=None,
        type_evidence_method="none",
        source_attribute=None,
        source_description=None,
    )
    assert validate(rows), "Unavailable type/source evidence must remain nullable."
    rows[0]["attributes"] = []
    assert validate(rows), "An active Object may have no active Attributes."
    assert not validate([])
    assert not validate([request_rows()[1]] * 26)
    for key, value in (
        ("sample_rows", [["private-synthetic-value"]]),
        ("attribute_id", 201),
        ("proposed_type", "BIGINT"),
    ):
        altered = deepcopy(request_rows())
        altered[1][key] = cast(JsonValue, value)
        assert not validate(altered), (
            "Undocumented fields cannot enter the typed evidence boundary."
        )
    wrong_kind = request_rows()
    wrong_kind[0]["kind"] = "attribute"
    assert not validate(wrong_kind)
    wrong_ref = request_rows()
    wrong_ref[1]["target_ref"] = "object:201"
    assert not validate(wrong_ref)
    unknown_method = request_rows()
    unknown_method[1]["type_evidence_method"] = "guessed_by_agent"
    assert not validate(unknown_method)


def test_assigned_refs_schema_has_exact_nonempty_unique_batch_refs() -> None:
    schema = contract("assigned_description_refs").value_schema
    validate = Draft202012Validator(schema).is_valid  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert schema["minItems"] == 1 and schema["maxItems"] == 25
    assert validate(["object:101", "attribute:201"])
    assert not validate([])
    assert not validate(["object:101", "object:101"])
    assert not validate(["attribute:0"])
    assert not validate(["attribute:201"] * 26)


def test_projection_preserves_legacy_values_and_emits_only_named_current_batch() -> None:
    rows = request_rows()
    context = cast(
        JsonValue,
        {"description_requests": rows, "private_full_snapshot": {"sentinel": "do-not-project"}},
    )
    old = {LEGACY: context, "workflow.validation_failures": [], "custom.legacy": {"keep": True}}
    baseline = deepcopy(old)
    result = project(context, legacy=old)
    assert result[REFS] == ["object:101", "attribute:201"]
    assert result[REQUESTS] == rows
    assert set(result) == {*old, REFS, REQUESTS}
    assert all(result[key] is value for key, value in old.items())
    assert old == baseline
    assert "private_full_snapshot" not in json.dumps(
        {REFS: result[REFS], REQUESTS: result[REQUESTS]}
    )
    assert project(context, legacy=result) == result


def test_projection_uses_only_registered_inputs_and_leaves_legacy_only_context_alone() -> None:
    context = cast(JsonValue, {"description_requests": request_rows()})
    result = project(context, selected_plan=plan(names=("assigned_description_refs",)))
    assert REFS in result and REQUESTS not in result
    malformed_legacy_context = cast(JsonValue, {"old_shape": ["preserve-original-meaning"]})
    legacy = {LEGACY: malformed_legacy_context}
    assert project(malformed_legacy_context, selected_plan=plan(names=()), legacy=legacy) == legacy


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "empty",
        "duplicate_ref",
        "too_many",
        "missing_nullable_field",
        "extra_sample_field",
        "wrong_kind_ref",
    ],
)
def test_invalid_new_input_is_rejected_without_silent_empty_fallback(defect: str) -> None:
    rows = request_rows()
    context: dict[str, JsonValue] = {"description_requests": cast(JsonValue, rows)}
    if defect == "missing":
        context = {}
    elif defect == "empty":
        context["description_requests"] = []
    elif defect == "duplicate_ref":
        rows.append(deepcopy(rows[1]))
    elif defect == "too_many":
        context["description_requests"] = [
            {**rows[1], "target_ref": f"attribute:{position + 1}"} for position in range(26)
        ]
    elif defect == "missing_nullable_field":
        del rows[1]["source_description"]
    elif defect == "extra_sample_field":
        rows[1]["sample_rows"] = [["sensitive-value-marker"]]
    elif defect == "wrong_kind_ref":
        rows[1]["target_ref"] = "object:201"
    with pytest.raises(InvalidRequestError) as captured:
        project(cast(JsonValue, context))
    assert "sensitive-value-marker" not in str(captured.value)
    assert "Source identifier" not in str(captured.value)


def test_catalog_cannot_resolve_inputs_on_an_unregistered_stage_or_mode() -> None:
    lookup = get_prompt_input_contract
    assert (
        lookup(
            model_workflow="metadata_enrichment",
            workflow_execution_mode="tool_assisted",
            stage_code="candidate_authoring",
            resolver_key=REQUESTS,
        )
        is None
    )
    assert (
        lookup(
            model_workflow="logical",
            workflow_execution_mode="one_shot",
            stage_code="candidate_authoring",
            resolver_key=REQUESTS,
        )
        is None
    )
    assert (
        lookup(
            model_workflow="metadata_enrichment",
            workflow_execution_mode="one_shot",
            stage_code="arbitrary",
            resolver_key=REQUESTS,
        )
        is None
    )


def test_new_projection_refuses_a_conflicting_existing_normalized_value() -> None:
    context = cast(JsonValue, {"description_requests": request_rows()})
    with pytest.raises(InvalidRequestError):
        project(context, legacy={LEGACY: context, REFS: ["attribute:999"]})


def test_optional_new_definitions_preserve_old_frozen_template_bytes() -> None:
    context = cast(JsonValue, {"description_requests": request_rows()})
    current = plan()
    templates = PromptComponentTemplates(
        system="Existing immutable instruction.", instruction="Original {{stage_context}}"
    )
    old_render = render_prompt(
        templates=templates,
        variables=current.stages[0].variables[:1],
        resolver_values={LEGACY: context},
    )
    new_render = render_prompt(
        templates=templates, variables=current.stages[0].variables, resolver_values=project(context)
    )
    assert (
        old_render.system == new_render.system and old_render.instruction == new_render.instruction
    )
    assert not new_render.warning_codes


def test_prompt_variable_dto_preserves_legacy_and_exposes_typed_help() -> None:
    legacy = dict(
        name="legacy",
        resolver_key="legacy.context",
        data_type="json",
        is_required=True,
        description="Existing help",
        example={},
        order=1,
    )
    result = PromptStageVariable.model_validate(legacy)
    assert result.model_dump()["value_schema"] is None
    descriptor = contract("description_requests")
    payload = {
        **legacy,
        **{
            key: getattr(descriptor, key)
            for key in (
                "name",
                "resolver_key",
                "data_type",
                "description",
                "example",
                "value_schema",
                "source",
                "availability",
                "delivery",
                "context_path",
            )
        },
    }
    documented = PromptStageVariable.model_validate(payload)
    assert documented.value_schema == descriptor.value_schema
    assert documented.context_path == "context.original_context.description_requests"


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["catalog", "template_detail"])
async def test_both_prompt_reads_expose_fixed_help_and_preserve_stored_legacy_values(
    surface: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    variable_rows = [
        {
            "name": name,
            "resolver_key": f"{PREFIX}.inputs.{name}",
            "data_type": "json",
            "is_required": False,
            "description": "Stored generic help",
            "example": None,
            "order": position + 30,
        }
        for position, name in enumerate(("assigned_description_refs", "description_requests"))
    ]
    if surface == "catalog":
        original = StageCatalogTransaction.fetch_all

        async def catalog_rows(self: Any, query: Any, parameters: Any = ()) -> Any:
            base = (await original(self, query, parameters))[0]
            base.update(
                model_workflow="metadata_enrichment", workflow_stage_code="candidate_authoring"
            )
            return [
                {**base, **{f"variable_{key}": value for key, value in row.items()}}
                for row in variable_rows
            ]

        monkeypatch.setattr(StageCatalogTransaction, "fetch_all", catalog_rows)
        database: Any = StageCatalogDatabase()
    else:
        original_one = TemplateDetailTransaction.fetch_one
        original_all = TemplateDetailTransaction.fetch_all

        async def detail_header(self: Any, query: Any, parameters: Any = ()) -> Any:
            row = await original_one(self, query, parameters)
            if row and "prompt_template_id" in row:
                row.update(
                    model_workflow="metadata_enrichment", workflow_stage_code="candidate_authoring"
                )
            return row

        async def detail_rows(self: Any, query: Any, parameters: Any = ()) -> Any:
            rows = await original_all(self, query, parameters)
            return (
                [*rows, *variable_rows] if "application.workflow_stage_variable" in query else rows
            )

        monkeypatch.setattr(TemplateDetailTransaction, "fetch_one", detail_header)
        monkeypatch.setattr(TemplateDetailTransaction, "fetch_all", detail_rows)
        database = TemplateDetailDatabase()

    service = DatabasePromptService(
        database=cast(PromptDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    if surface == "catalog":
        response = await service.list_stages(PRINCIPAL, tenant_id=7)
        variables = response.items[0].allowed_variables
    else:
        detail = await service.read_template(PRINCIPAL, tenant_id=7, prompt_template_id=101)
        variables = detail.allowed_variables
        legacy = variables[0]
        assert legacy.description == "Governed source context" and legacy.example is None
        assert legacy.model_dump()["value_schema"] is None
        assert detail.versions[0].system_prompt_template == "RAW_SYSTEM_SENTINEL {{stage_context}}"
        assert database.transaction.calls == ["authorize", "header", "variables", "versions"]
    for name in ("assigned_description_refs", "description_requests"):
        variable = next(item for item in variables if item.name == name)
        descriptor = contract(name)
        assert variable.model_dump()["value_schema"] == descriptor.value_schema
        assert variable.description == descriptor.description
        assert variable.example == descriptor.example
        assert variable.model_dump()["delivery"] == descriptor.delivery


class DescriptionOnlyExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.calls += 1
        assert "{{" not in request.system_prompt + request.instruction_prompt
        assert '"object:101"' in request.instruction_prompt
        assert '"attribute:201"' in request.instruction_prompt
        assert "Source identifier" in request.instruction_prompt
        assert not request.allowed_tool_names
        return AgentExecutionResult(
            candidate={
                "descriptions": {
                    "object:101": "Sales transactions received from the source application.",
                    "attribute:201": "Stable source identifier for each sales transaction.",
                }
            },
            turn_count=1,
            tool_call_count=0,
        )


@pytest.mark.asyncio
async def test_real_stage_runner_projects_custom_named_inputs_before_shared_repair() -> None:
    current = plan()
    executor = DescriptionOnlyExecutor()
    runner = AgentStageRunner(
        executor=executor,
        policy=AgentContextPolicy(
            one_shot_max_context_bytes=32_768,
            stage_max_context_bytes=32_768,
            max_candidate_bytes=32_768,
            max_validation_issues=20,
        ),
    )
    context = cast(JsonValue, {"description_requests": request_rows()})
    validator = DescriptionValidator({"object:101": "orders", "attribute:201": "order_id"})
    result = await runner.run(
        plan=current,
        stage_code="candidate_authoring",
        resolver_values={LEGACY: context, "workflow.validation_failures": []},
        context=context,
        output_schema=validator.output_schema(),
        allowed_tool_names=(),
        validator=validator,
    )
    assert executor.calls == 1 and result.attempt_count == 1
    assert not result.warning_codes
