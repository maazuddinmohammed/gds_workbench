"""Compose configured Agent execution without provider I/O."""

from __future__ import annotations

from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.capabilities import AgentCapabilityRegistry
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionAdapter,
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentExecutionRouter,
)
from gds_workbench_api.integrations.agents.adapters import (
    LangChainCreateAgentAdapter,
    OpenAIAgentsSdkAdapter,
)
from gds_workbench_api.integrations.agents.configuration import AgentRuntimeConfiguration
from gds_workbench_api.integrations.agents.fake_conceptual import (
    detailed_conceptual_candidate,
)
from gds_workbench_api.integrations.agents.fake_dimensional import (
    detailed_dimensional_candidate,
    fake_dimensional_candidate,
)
from gds_workbench_api.integrations.agents.fake_logical import (
    detailed_logical_candidate,
    fake_logical_candidate,
)
from gds_workbench_api.integrations.agents.fake_mapping import (
    fake_detailed_mapping_candidate,
    fake_mapping_attribute_batch,
    fake_mapping_batch_plans,
    fake_mapping_context_from_tools,
    fake_mapping_header_candidate,
    mapping_dict,
)
from gds_workbench_api.integrations.agents.fake_shared import (
    analysis_selected_attributes,
    code_generation_target_refs,
    conceptual_source_objects,
    detailed_original_context,
    tool_assisted_conceptual_sources,
    tool_assisted_logical_sources,
)


class LocalFakeAgentAdapter:
    """Deterministic local boundary with no external I/O or prompt/tool-output echo."""

    def __init__(self, *, sdk_code: str) -> None:
        self.sdk_code = sdk_code

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        if request.execution_mode == "detailed_coverage" and (
            request.allowed_tool_names or request.local_tool_catalog is not None
        ):
            raise InvalidRequestError("The local fake does not support this agent execution path.")
        if request.execution_mode == "one_shot" and (
            request.allowed_tool_names or request.local_tool_catalog is not None
        ):
            raise InvalidRequestError("The local fake does not support this agent execution path.")
        if request.execution_mode == "tool_assisted" and (
            request.local_tool_catalog is None
            or request.allowed_tool_names
            != tuple(definition.name for definition in request.local_tool_catalog.definitions)
        ):
            raise InvalidRequestError("The local fake does not support this agent execution path.")
        tool_call_count = 0
        if request.workflow == "mapping" and request.execution_mode == "detailed_coverage":
            candidate = fake_detailed_mapping_candidate(request)
        elif request.workflow == "mapping" and request.stage == "mapping_authoring":
            if request.execution_mode == "tool_assisted":
                mapping_context, tool_call_count = fake_mapping_context_from_tools(request)
            elif request.execution_mode == "one_shot":
                mapping_context = detailed_original_context(request.context)
            else:
                raise InvalidRequestError(
                    "The local fake does not support this agent execution path."
                )
            header = fake_mapping_header_candidate(
                context=mapping_context,
                output_schema=request.output_schema,
            )
            package = mapping_dict(header.get("package"))
            candidate = cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "header": header,
                    "attribute_batches": [
                        fake_mapping_attribute_batch(
                            context=mapping_context,
                            package=package,
                            batch_plan=batch_plan,
                            output_schema=request.output_schema,
                        )
                        for batch_plan in fake_mapping_batch_plans(
                            context=mapping_context,
                            package=package,
                        )
                    ],
                },
            )
        elif request.workflow == "code_generation" and request.stage == "sql_generation":
            target_refs = code_generation_target_refs(request.context)
            candidate = cast(
                JsonValue,
                {
                    "artifacts": [
                        {
                            "target_ref": target_ref,
                            "generated_sql": f"SELECT {position};\n",
                        }
                        for position, target_ref in enumerate(target_refs, start=1)
                    ]
                },
            )
        elif request.workflow == "analysis_inference" and request.stage == "relationship_inference":
            attributes = analysis_selected_attributes(request.context)
            relationships: list[dict[str, JsonValue]] = []
            if len(attributes) >= 2:
                source, target = attributes[:2]
                relationships.append(
                    {
                        **{f"from_{name}": value for name, value in source.items()},
                        **{f"to_{name}": value for name, value in target.items()},
                        "relationship_kind": "reference",
                        "relationship_confidence": "medium",
                        "relationship_basis": (
                            "Selected Attribute metadata supports this candidate."
                        ),
                    }
                )
            candidate = cast(JsonValue, {"relationships": relationships})
        elif request.workflow == "dimensional" and request.execution_mode == "detailed_coverage":
            candidate = detailed_dimensional_candidate(request)
        elif request.workflow == "dimensional" and request.stage == "candidate_authoring":
            if request.execution_mode == "tool_assisted":
                source_objects, source_attributes, tool_call_count = tool_assisted_logical_sources(
                    request
                )
            elif request.execution_mode == "one_shot":
                source_objects = conceptual_source_objects(request.context)
                source_attributes = analysis_selected_attributes(request.context)
            else:
                raise InvalidRequestError(
                    "The local fake does not support this agent execution path."
                )
            candidate = fake_dimensional_candidate(
                source_objects=source_objects,
                source_attributes=source_attributes,
            )
        elif request.workflow == "logical" and request.execution_mode == "detailed_coverage":
            candidate = detailed_logical_candidate(request)
        elif request.workflow == "logical" and request.stage == "candidate_authoring":
            if request.execution_mode == "tool_assisted":
                source_objects, source_attributes, tool_call_count = tool_assisted_logical_sources(
                    request
                )
            elif request.execution_mode == "one_shot":
                source_objects = conceptual_source_objects(request.context)
                source_attributes = analysis_selected_attributes(request.context)
            else:
                raise InvalidRequestError(
                    "The local fake does not support this agent execution path."
                )
            candidate = fake_logical_candidate(
                source_objects=source_objects,
                source_attributes=source_attributes,
            )
        elif request.workflow == "conceptual" and request.execution_mode == "detailed_coverage":
            candidate = detailed_conceptual_candidate(request)
        elif request.workflow == "conceptual" and request.stage == "candidate_authoring":
            if request.execution_mode == "tool_assisted":
                source_objects, tool_call_count = tool_assisted_conceptual_sources(request)
            else:
                source_objects = conceptual_source_objects(request.context)
            candidate = cast(
                JsonValue,
                {
                    "objects": [
                        {
                            "conceptual_object_name": f"Conceptual Entity {position}",
                            "conceptual_object_definition": (
                                "A locally generated Conceptual entity candidate."
                            ),
                            "conceptual_object_type": "entity",
                            "conceptual_object_grain": "One governed business entity.",
                            "conceptual_object_aliases": [],
                            "conceptual_object_confidence": "medium",
                            "conceptual_object_status": "needs_review",
                            "conceptual_object_is_locked": False,
                            "supports": [
                                {
                                    "support_source_type": "object",
                                    "source_object": source_object,
                                    "support_role": "source",
                                    "support_reason": ("Selected Object supports this candidate."),
                                    "support_reason_detail": None,
                                    "support_confidence": "medium",
                                    "support_status": "active",
                                    "support_is_locked": False,
                                }
                            ],
                        }
                        for position, source_object in enumerate(
                            source_objects,
                            start=1,
                        )
                    ],
                    "relationships": [],
                },
            )
        else:
            raise InvalidRequestError("The local fake does not support this agent execution path.")
        return AgentExecutionResult(
            candidate=candidate,
            turn_count=1,
            tool_call_count=tool_call_count,
        )

    def __repr__(self) -> str:
        return f"LocalFakeAgentAdapter(sdk_code={self.sdk_code!r})"


def create_agent_execution_router(
    *,
    configuration: AgentRuntimeConfiguration,
    capabilities: AgentCapabilityRegistry,
) -> AgentExecutionRouter:
    adapters: tuple[AgentExecutionAdapter, ...]
    if configuration.mode == "fake":
        adapters = tuple(LocalFakeAgentAdapter(sdk_code=sdk.code) for sdk in capabilities.sdks)
    else:
        adapters = (
            LangChainCreateAgentAdapter(connections=configuration.connections),
            OpenAIAgentsSdkAdapter(connections=configuration.connections),
        )
    return AgentExecutionRouter(capabilities=capabilities, adapters=adapters)
