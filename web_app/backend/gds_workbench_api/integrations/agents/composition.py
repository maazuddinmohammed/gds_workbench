"""Compose configured Agent execution without provider I/O."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.capabilities import (
    AgentCapabilityRegistry,
    select_agent_runtime_capabilities,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionAdapter,
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentExecutionRouter,
)
from gds_workbench_api.features.workflows.usage.contracts import AgentUsageRecorder
from gds_workbench_api.integrations.agents.adapters import (
    FoundryApiKeyAuthentication,
    FoundryModelAuthentication,
    ManagedModelAuthentication,
    OpenAIAgentsSdkAdapter,
)
from gds_workbench_api.integrations.agents.configuration import AgentRuntimeConfiguration
from gds_workbench_api.integrations.agents.fake_dimensional import (
    fake_dimensional_candidate,
)
from gds_workbench_api.integrations.agents.fake_logical import (
    fake_logical_candidate,
)
from gds_workbench_api.integrations.agents.fake_mapping import (
    fake_mapping_candidate,
    fake_mapping_context_from_tools,
)
from gds_workbench_api.integrations.agents.fake_shared import (
    analysis_selected_attributes,
    code_generation_target_refs,
    conceptual_source_objects,
    original_context,
    tool_assisted_conceptual_sources,
    tool_assisted_logical_sources,
)


class LocalFakeAgentAdapter:
    """Deterministic local boundary with no external I/O or prompt/tool-output echo."""

    def __init__(self, *, sdk_code: str) -> None:
        self.sdk_code = sdk_code

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
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
        if request.workflow == "metadata_enrichment" and request.stage == "candidate_authoring":
            properties = request.output_schema.get("properties")
            description_schema = (
                properties.get("descriptions") if isinstance(properties, dict) else None
            )
            refs = (
                description_schema.get("required") if isinstance(description_schema, dict) else None
            )
            if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
                raise InvalidRequestError("The local enrichment target schema is unavailable.")
            descriptions: dict[str, JsonValue] = {}
            for ref in refs:
                if not isinstance(ref, str):
                    continue
                try:
                    key = cast(JsonValue, json.loads(ref))
                    name = key[-1] if isinstance(key, list) and key else ref
                except ValueError:
                    name = ref
                descriptions[ref] = f"Synthetic local description for {name}."
            candidate = cast(JsonValue, {"descriptions": descriptions})
        elif request.workflow == "mapping":
            if request.stage == "mapping_authoring" and request.execution_mode == "tool_assisted":
                mapping_context, tool_call_count = fake_mapping_context_from_tools(request)
                candidate = fake_mapping_candidate(mapping_context)
            elif request.stage == "mapping_authoring" and request.execution_mode == "one_shot":
                mapping_context = original_context(request.context)
                candidate = fake_mapping_candidate(mapping_context)
            else:
                raise InvalidRequestError(
                    "The local fake does not support this agent execution path."
                )
        elif request.workflow == "code_generation" and request.stage == "sql_generation":
            target_systems: dict[str, list[JsonValue]]
            code_context = original_context(request.context)
            if code_context.get("__gds_downstream_inputs__") == "code_generation":
                values = cast(dict[str, JsonValue], code_context["values"])
                target_ref = values.get("target_ref")
                systems = values.get("source_systems")
                if not isinstance(target_ref, str) or not isinstance(systems, list):
                    raise InvalidRequestError("The local Code context is unavailable.")
                target_systems = {
                    target_ref: [
                        row["system_code"]
                        for row in systems
                        if isinstance(row, dict) and isinstance(row.get("system_code"), str)
                    ],
                }
            else:
                target_systems = {
                    target_ref: [] for target_ref in code_generation_target_refs(request.context)
                }
            candidate = cast(
                JsonValue,
                {
                    "artifacts": [
                        {
                            "target_ref": target_ref,
                            **(
                                {
                                    "artifact_name": f"{target_ref}.sql",
                                    "artifact_role": "target_transformation",
                                    "source_system_codes": system_codes,
                                }
                                if code_context.get("__gds_downstream_inputs__")
                                == "code_generation"
                                else {}
                            ),
                            "generated_sql": f"SELECT {position};\n",
                        }
                        for position, (target_ref, system_codes) in enumerate(
                            target_systems.items(), start=1
                        )
                    ]
                },
            )
        elif request.workflow == "validation" and request.stage == "validation_generation":
            validation_context = original_context(request.context)
            if validation_context.get("__gds_downstream_inputs__") == "validation":
                validation_context = cast(dict[str, JsonValue], validation_context["values"])
            system_ref = validation_context.get("system_ref")
            if not isinstance(system_ref, str):
                raise InvalidRequestError(
                    "The local fake does not support this agent execution path."
                )
            candidate = cast(
                JsonValue,
                {
                    "system_ref": system_ref,
                    "validation_groups": [
                        {
                            "validation_group_name": "technical_execution",
                            "validation_group_description": (
                                "Basic executable validation for the selected System."
                            ),
                            "validation_checks": [
                                {
                                    "validation_check_name": "validation_session_executes",
                                    "validation_check_description": (
                                        "Confirms the governed validation query executes."
                                    ),
                                    "validation_category_code": "technical.execution",
                                    "validation_severity": "blocking",
                                    "validation_query_sql": "SELECT 1",
                                    "validation_comparison_query_sql": None,
                                    "validation_result_data_type": None,
                                    "validation_comparison_operator": ("executes_successfully"),
                                    "validation_comparison_value_type": "none",
                                    "validation_comparison_value": None,
                                }
                            ],
                        }
                    ],
                },
            )
        elif request.workflow == "analysis_inference" and request.stage == "relationship_inference":
            if request.execution_mode == "tool_assisted":
                _source_objects, attributes, tool_call_count = tool_assisted_logical_sources(
                    request
                )
            elif request.execution_mode == "one_shot":
                attributes = analysis_selected_attributes(request.context)
            else:
                raise InvalidRequestError(
                    "The local fake does not support this agent execution path."
                )
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
                            "conceptual_object_name": "BusinessConcept",
                            "conceptual_object_definition": (
                                "A compact locally generated business concept supported "
                                "by the selected scope."
                            ),
                            "conceptual_object_type": "business_concept",
                            "conceptual_object_grain": (
                                "A stable business subject represented across the selected scope."
                            ),
                            "conceptual_object_aliases": [],
                            "conceptual_object_confidence": "medium",
                            "conceptual_object_status": "active",
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
                                for source_object in source_objects
                            ],
                        }
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
    provider_authentications: Mapping[str, ManagedModelAuthentication] | None = None,
    usage_recorder: AgentUsageRecorder | None = None,
) -> AgentExecutionRouter:
    adapters: tuple[AgentExecutionAdapter, ...]
    registered_deployments = {
        (model.provider_code, model.code): model.deployment_name for model in capabilities.models
    }
    for connection in configuration.connections:
        connection_key = (connection.provider_code, connection.model_code)
        if connection_key not in registered_deployments:
            raise ValueError("A configured Agent model deployment is not registered")
        if registered_deployments[connection_key] != connection.model_endpoint:
            raise ValueError(
                "The configured Agent model deployment does not match the Agent registry"
            )
    runtime_capabilities = (
        capabilities
        if configuration.mode == "fake"
        else select_agent_runtime_capabilities(
            capabilities,
            configured_models={
                (connection.provider_code, connection.model_code)
                for connection in configuration.connections
            },
        )
    )
    configured_provider_codes = {
        connection.provider_code for connection in configuration.connections
    }
    authentications = {} if provider_authentications is None else dict(provider_authentications)
    if provider_authentications is not None and set(authentications) != configured_provider_codes:
        raise ValueError(
            "Every configured Agent provider requires exactly one authentication adapter"
        )
    if configuration.mode == "fake":
        adapters = tuple(
            LocalFakeAgentAdapter(sdk_code=sdk.code) for sdk in runtime_capabilities.sdks
        )
    else:
        if provider_authentications is None:
            for provider_code in configured_provider_codes:
                provider_connections = tuple(
                    connection
                    for connection in configuration.connections
                    if connection.provider_code == provider_code
                )
                connection = provider_connections[0]
                resource_configuration = (
                    connection.openai_base_url,
                    connection.token_scope,
                    connection.foundry_client_credentials,
                    connection.foundry_api_key,
                )
                if any(
                    (
                        candidate.openai_base_url,
                        candidate.token_scope,
                        candidate.foundry_client_credentials,
                        candidate.foundry_api_key,
                    )
                    != resource_configuration
                    for candidate in provider_connections[1:]
                ):
                    raise ValueError(
                        "Foundry model deployments must share one resource and authentication"
                    )
                if connection.openai_base_url is None:
                    raise ValueError("Foundry authentication configuration is incomplete")
                if connection.foundry_api_key is not None:
                    if (
                        connection.token_scope is not None
                        or connection.foundry_client_credentials is not None
                    ):
                        raise ValueError("Foundry authentication configuration is incomplete")
                    authentications[provider_code] = FoundryApiKeyAuthentication(
                        base_url=connection.openai_base_url,
                        api_key=connection.foundry_api_key,
                    )
                else:
                    if (
                        connection.token_scope is None
                        or connection.foundry_client_credentials is None
                    ):
                        raise ValueError("Foundry authentication configuration is incomplete")
                    credentials = connection.foundry_client_credentials
                    authentications[provider_code] = FoundryModelAuthentication(
                        base_url=connection.openai_base_url,
                        token_scope=connection.token_scope,
                        tenant_id=str(credentials.tenant_id),
                        client_id=str(credentials.client_id),
                        client_secret=credentials.client_secret,
                    )
        configured_adapters: list[AgentExecutionAdapter] = []
        for sdk in runtime_capabilities.sdks:
            if sdk.code == "openai_agents_sdk":
                configured_adapters.append(
                    OpenAIAgentsSdkAdapter(
                        connections=configuration.connections,
                        model_authentications=authentications,
                    )
                )
            else:
                raise ValueError("The configured Agent SDK is unsupported")
        adapters = tuple(configured_adapters)
    return AgentExecutionRouter(
        capabilities=runtime_capabilities,
        adapters=adapters,
        resources=tuple(authentications.values()),
        usage_recorder=usage_recorder,
    )
