from __future__ import annotations

from typing import cast

import pytest
from gds_etl_workbench.domain.modeling_records import PhysicalAttributeKey
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.analysis.candidate import (
    AnalysisInferenceCandidateValidator,
    AnalysisInferenceRelationship,
)
from gds_workbench_api.features.analysis.detailed import (
    DetailedAnalysisCandidateFinderValidator,
    DetailedAnalysisReconciliationValidator,
    DetailedAnalysisRelationshipResolverValidator,
    DetailedAnalysisReviewerValidator,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
)
from gds_workbench_api.integrations.agents.composition import LocalFakeAgentAdapter


def _selection(sdk_code: str) -> AgentRunSelection:
    return AgentRunSelection(
        sdk_code=sdk_code,
        provider_code="databricks",
        model_code="databricks-primary",
        reasoning_effort_code="medium",
        max_turns=10,
        validation_retry_count=2,
    )


def _attribute(object_name: str) -> PhysicalAttributeKey:
    return PhysicalAttributeKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name=object_name,
        attribute_name="customer_id",
    )


def _request(
    *,
    sdk_code: str,
    stage: str,
    context: JsonValue,
    output_schema: dict[str, JsonValue],
) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="analysis_inference",
        stage=stage,
        execution_mode="detailed_coverage",
        selection=_selection(sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        context={"original_context": context, "repair": None},
        output_schema=output_schema,
        allowed_tool_names=(),
    )


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
@pytest.mark.asyncio
async def test_local_fake_supports_complete_detailed_analysis_sequence(
    sdk_code: str,
) -> None:
    adapter = LocalFakeAgentAdapter(sdk_code=sdk_code)
    selected = (_attribute("order_raw"), _attribute("customer_raw"))
    finder_validator = DetailedAnalysisCandidateFinderValidator(
        slice_ref="slice_00001",
        allowed_attributes=selected,
    )
    selected_objects = [
        {
            "selection_order": position,
            "object": {
                "tenant_code": attribute.tenant_code,
                "system_code": attribute.system_code,
                "connection_code": attribute.connection_code,
                "object_schema": attribute.object_schema,
                "object_name": attribute.object_name,
            },
            "attributes": [attribute.model_dump(mode="json")],
        }
        for position, attribute in enumerate(selected, start=1)
    ]
    finder_result = await adapter.execute(
        _request(
            sdk_code=sdk_code,
            stage="candidate_finder",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "slice_ref": "slice_00001",
                    "selected_objects": selected_objects,
                },
            ),
            output_schema=finder_validator.output_schema(),
        )
    )
    assert (await finder_validator.validate(finder_result.candidate)).issues == ()
    finder = finder_validator.parse_validated(finder_result.candidate)

    resolver_validator = DetailedAnalysisRelationshipResolverValidator(
        candidates=finder.candidates
    )
    resolver_result = await adapter.execute(
        _request(
            sdk_code=sdk_code,
            stage="relationship_resolver",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "candidate_finder_result": finder.model_dump(mode="json"),
                },
            ),
            output_schema=resolver_validator.output_schema(),
        )
    )
    assert (await resolver_validator.validate(resolver_result.candidate)).issues == ()
    resolution = resolver_validator.parse_validated(resolver_result.candidate)

    final_validator = AnalysisInferenceCandidateValidator(
        selected_attribute_keys=selected,
        applied=(),
    )
    reconciliation_validator = DetailedAnalysisReconciliationValidator(
        decisions=resolution.decisions,
        applied_by_ref={},
        final_validator=final_validator,
    )
    reconciliation_result = await adapter.execute(
        _request(
            sdk_code=sdk_code,
            stage="whole_slice_reconciler",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "resolutions": [resolution.model_dump(mode="json")],
                    "applied_records": [],
                },
            ),
            output_schema=reconciliation_validator.output_schema(),
        )
    )
    assert (
        await reconciliation_validator.validate(reconciliation_result.candidate)
    ).issues == ()
    reconciled = reconciliation_validator.materialize_validated(
        reconciliation_result.candidate
    )
    raw_relationships = cast(dict[str, list[dict[str, JsonValue]]], reconciled)[
        "relationships"
    ]

    parsed_reconciliation = cast(dict[str, object], reconciliation_result.candidate)
    typed_relationships = tuple(
        AnalysisInferenceRelationship.model_validate(item, strict=True)
        for item in cast(
            list[dict[str, JsonValue]], parsed_reconciliation["relationships"]
        )
    )
    reviewer_validator = DetailedAnalysisReviewerValidator(
        relationships=typed_relationships,
        applied_record_refs=(),
    )
    reviewer_result = await adapter.execute(
        _request(
            sdk_code=sdk_code,
            stage="analysis_reviewer",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "relationships": [
                        {
                            "relationship_ref": reference,
                            "relationship": relationship,
                        }
                        for reference, relationship in zip(
                            reviewer_validator.relationship_refs,
                            raw_relationships,
                            strict=True,
                        )
                    ],
                    "required_applied_record_refs": [],
                },
            ),
            output_schema=reviewer_validator.output_schema(),
        )
    )
    assert (await reviewer_validator.validate(reviewer_result.candidate)).issues == ()
    assert reviewer_validator.parse_validated(reviewer_result.candidate).findings == ()
