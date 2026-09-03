from __future__ import annotations

import json
from typing import cast

import pytest
from jsonschema.validators import validator_for
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import Tool

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.server import create_mcp_server
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode, RuntimeSettings
from gds_etl_workbench.infrastructure.postgres import Database
from gds_etl_workbench.application.change_sets.contracts import decode_canonical_base64_fragment
from gds_etl_workbench.domain.snapshots.metadata import (
    DATASETS_BY_NAME as METADATA_DATASETS_BY_NAME,
)
from gds_etl_workbench.domain.snapshots.model import DATASETS_BY_NAME
from gds_etl_workbench.tools.snapshots.model.describe_model_dataset import (
    register_describe_model_dataset_tool,
)

EXPECTED_PUBLIC_TOOLS = {
    "list_tenants",
    "get_tenant_details",
    "list_models",
    "get_model_input_scope",
    "check_tenant_lock",
    "acquire_tenant_lock",
    "renew_tenant_lock",
    "release_tenant_lock",
    "override_tenant_lock",
    "create_metadata_change_set",
    "stage_metadata_change_set",
    "begin_metadata_stage_batch",
    "put_metadata_stage_chunk",
    "commit_metadata_stage_batch",
    "get_metadata_change_set",
    "validate_metadata_change_set",
    "apply_metadata_change_set",
    "archive_metadata_change_set",
    "create_model_change_set",
    "stage_model_change_set",
    "begin_model_stage_batch",
    "put_model_stage_chunk",
    "commit_model_stage_batch",
    "get_model_change_set",
    "validate_model_change_set",
    "apply_model_change_set",
    "archive_model_change_set",
    "inspect_metadata",
    "read_model_section",
    "execute_databricks_sql",
    "describe_model_dataset",
    "create_model_snapshot",
    "export_model_dbml",
    "describe_metadata_dataset",
    "create_metadata_snapshot",
}


class SchemaDatabase:
    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def expire_tenant_locks(self) -> int:
        return 0

    async def append_tool_call_log(self, _record: object) -> None:
        return None


def settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_ENVIRONMENT": "local",
            "GDS_DATABASE_DSN": "postgresql://unused@invalid.example.invalid/unused",
            "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_LOCAL_PRINCIPAL_OBJECT_ID": "33333333-3333-3333-3333-333333333333",
            "GDS_MCP_PUBLIC_URL": "https://testserver/mcp",
            "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": (
                "https://snapshot.blob.core.windows.net"
            ),
            "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
        }
    )


def server() -> MCPServer[None]:
    runtime_settings = settings()
    return create_mcp_server(
        runtime_settings,
        cast(Database, SchemaDatabase()),
        IdentityProvider(runtime_settings.auth_mode),
    )


async def list_tools() -> list[Tool]:
    async with Client(server()) as client:
        return (await client.list_tools()).tools


def model_description_server() -> MCPServer[None]:
    database = cast(Database, SchemaDatabase())
    identity = IdentityProvider(AuthMode.DEV)
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=AuthorizationService(),
    )
    result = MCPServer[None](name="model-description-test")
    register_describe_model_dataset_tool(
        result,
        identity_provider=identity,
        audit=audit,
    )
    return result


@pytest.mark.asyncio
async def test_public_surface_is_exactly_35_focused_tools() -> None:
    names = {tool.name for tool in await list_tools()}

    assert names == EXPECTED_PUBLIC_TOOLS
    assert len(names) == 35
    assert (
        not {
            "get_model",
            "get_model_snapshot",
            "get_model_dbml",
            "get_metadata_snapshot",
            "get_server_contract",
            "get_model_scope",
            "get_model_mapping_document",
            "get_model_code_generation_document",
            "validate_and_materialize_mapping_candidate",
            "qa_authoring_context",
        }
        & names
    )


@pytest.mark.asyncio
async def test_tool_descriptions_and_complex_arguments_are_agent_ready() -> None:
    tools = {tool.name: tool for tool in await list_tools()}

    for tool in tools.values():
        assert tool.description is not None
        assert 8 <= len(tool.description.split()) <= 90, tool.name

    inspect = tools["inspect_metadata"].input_schema["properties"]
    assert "objects requires zone" in inspect["view"]["description"]
    assert "Required Object ID" in inspect["object_id"]["description"]

    begin = tools["begin_model_stage_batch"].input_schema["properties"]
    assert "generated_code" in begin["payload_mode"]["description"]
    assert "concatenated in chunk order" in begin["batch_sha256"]["description"]

    put = tools["put_model_stage_chunk"].input_schema["properties"]
    assert "base64 fragment" in put["payload_fragment_base64"]["description"]

    execute = tools["execute_databricks_sql"].input_schema["properties"]
    assert execute["environment_code"]["default"] == "dev"
    assert "defaults to lowercase dev" in execute["environment_code"]["description"]

    connection = tools["get_tenant_details"].output_schema["$defs"][
        "TenantConnectionSummary"
    ]["properties"]
    assert (
        "exact Bronze/Silver/Gold placement"
        in connection["is_tenant_gds_connection"]["description"]
    )

    assert "explicitly requests DBML" in tools["export_model_dbml"].description
    for tool_name in ("stage_metadata_change_set", "stage_model_change_set"):
        assert "every included dataset fits in one request" in tools[tool_name].description
    for tool_name in ("validate_metadata_change_set", "validate_model_change_set"):
        assert "invalid draft remains active" in tools[tool_name].description.lower()


@pytest.mark.asyncio
async def test_change_set_tools_advertise_exact_model_and_metadata_registries() -> None:
    tools = {tool.name: tool for tool in await list_tools()}

    for tool_name in (
        "stage_model_change_set",
        "begin_model_stage_batch",
        "put_model_stage_chunk",
    ):
        advertised = tools[tool_name].input_schema["$defs"]["ModelChangeSetDataset"][
            "enum"
        ]
        assert advertised == list(DATASETS_BY_NAME)
    for tool_name in ("get_model_change_set", "describe_model_dataset"):
        advertised = tools[tool_name].input_schema["$defs"]["ModelDataset"]["enum"]
        assert advertised == list(DATASETS_BY_NAME)

    metadata = tools["describe_metadata_dataset"].input_schema
    assert metadata["$defs"]["MetadataDataset"]["enum"] == list(
        METADATA_DATASETS_BY_NAME
    )


@pytest.mark.asyncio
async def test_focused_model_reader_excludes_broad_code_and_validation_payloads() -> (
    None
):
    tools = {tool.name: tool for tool in await list_tools()}
    readable = set(
        tools["read_model_section"].input_schema["$defs"]["ReadableModelDataset"][
            "enum"
        ]
    )

    assert {"model_object_binding", "model_attribute_binding"} <= readable
    assert {"mapping_dependency", "mapping_object", "mapping_attribute"} <= readable
    assert (
        not {
            "generated_code",
            "generated_code_source_system",
            "validation_group",
            "validation_check",
        }
        & readable
    )
    assert "get_model_input_scope" in tools


@pytest.mark.asyncio
async def test_describe_model_dataset_explains_every_public_column() -> None:
    async with Client(model_description_server()) as client:
        results = {
            dataset: await client.call_tool(
                "describe_model_dataset",
                {"dataset": dataset, "detail": "full"},
            )
            for dataset in DATASETS_BY_NAME
        }

    for dataset, result in results.items():
        assert result.is_error is False, dataset
        document = result.structured_content
        assert document is not None
        schema = document["record_schema"]
        assert document["change_set_eligible"] is True
        assert [column["name"] for column in document["columns"]] == list(
            schema["properties"]
        )
        assert all(column["description"].strip() for column in document["columns"])
        assert all(
            column["population_guidance"].strip() for column in document["columns"]
        )

    generated = results["generated_code"].structured_content["record_schema"]
    assert "artifact_name" in generated["properties"]
    assert "mapping_context_digest" not in generated["properties"]
    validation = results["validation_group"].structured_content["record_schema"]
    assert "mapping_context_digest" not in validation["properties"]
    assert "code_context_digest" not in validation["properties"]


@pytest.mark.asyncio
async def test_all_advertised_input_and_output_schemas_are_valid_json_schema() -> None:
    for tool in await list_tools():
        for schema_kind, schema in (
            ("input", tool.input_schema),
            ("output", tool.output_schema),
        ):
            assert schema is not None, f"{tool.name} has no {schema_kind} schema"
            validator_for(schema).check_schema(schema)


@pytest.mark.asyncio
async def test_public_schemas_exclude_removed_and_web_only_contracts() -> None:
    forbidden_fragments = {
        "application.",
        "default_agent_",
        "generated_sql_artifact",
        "mapping_package_document",
        "mapping_profile_key",
        "prompt_assignment",
        "prompt_template",
        "qa_authoring_context",
        "server_contract",
        "tool_contract_sha256",
        "workflow_run_id",
    }

    for tool in await list_tools():
        contract = json.dumps(
            {"input": tool.input_schema, "output": tool.output_schema},
            sort_keys=True,
        ).casefold()
        exposed = sorted(item for item in forbidden_fragments if item in contract)
        assert exposed == [], f"{tool.name} exposes removed fields: {exposed}"


@pytest.mark.asyncio
async def test_execute_databricks_sql_remains_the_only_governed_sql_tool() -> None:
    tools = {tool.name: tool for tool in await list_tools()}
    sql_tools = {name for name in tools if "sql" in name}

    assert sql_tools == {"execute_databricks_sql"}
    execute = tools["execute_databricks_sql"]
    assert set(execute.input_schema["required"]) == {
        "connection_id",
        "sql",
    }
    assert execute.input_schema["properties"]["environment_code"]["default"] == "dev"
    assert execute.output_schema is not None
    assert "environment_code" in execute.output_schema["properties"]


@pytest.mark.parametrize("value", ["", "YQ", "YR==", "YQ==\n", "YQ==="])
def test_stage_fragments_require_strict_canonical_base64(value: str) -> None:
    with pytest.raises(ValueError, match="fragment is invalid"):
        decode_canonical_base64_fragment(value)

    assert decode_canonical_base64_fragment("YQ==") == b"a"


@pytest.mark.asyncio
async def test_mcp_has_no_public_prompts() -> None:
    async with Client(server()) as client:
        listed = await client.list_prompts()

    assert listed.prompts == []


@pytest.mark.asyncio
async def test_mcp_has_no_public_resources() -> None:
    async with Client(server()) as client:
        listed = await client.list_resources()

    assert listed.resources == []


def test_server_instructions_state_the_simple_authoring_boundary() -> None:
    instructions = server().instructions
    assert instructions is not None
    text = " ".join(instructions.split())

    assert "Metadata registration must Apply before Model Binding" in text
    assert "Model Input Scope must Apply before Profiling or model development" in text
    assert "Metadata registration must Apply before Model Binding" in text
    assert "Binding must Apply before Mapping" in text
    assert "Mapping must Apply before Code or Validation" in text
    assert "Clients own interaction and workflow orchestration" in text
    assert "Tenant Lock ownership, revision fencing, idempotency" in text
    assert "Lock override and Apply are separate high-impact operations" in text
    assert "revision mismatch" in text
    assert "Metadata has no Tenant-wide revision" in text
    assert "environment_code=dev" in text
    assert "execute_databricks_sql" in text
    assert "acknowledgement" not in text
    assert "Workbench" not in text
    assert "Stage plan" not in text
    assert "capable local client" not in text
