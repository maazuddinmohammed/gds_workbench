from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from jsonschema.validators import validator_for
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import Tool

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.server import (
    MCP_SERVER_VERSION,
    create_mcp_server,
    tool_contract_sha256,
)
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode, RuntimeSettings
from gds_etl_workbench.infrastructure.postgres import Database
from gds_etl_workbench.tools.change_sets.common import decode_canonical_base64_fragment
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS_BY_NAME
from gds_etl_workbench.tools.snapshots.model.contracts import (
    DATASETS_BY_NAME as MODEL_DATASETS_BY_NAME,
)
from gds_etl_workbench.tools.snapshots.model.describe_model_dataset import (
    register_describe_model_dataset_tool,
)
from gds_etl_workbench.tools.server_contract import register_server_contract_tool


class _SchemaDatabase:
    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def expire_tenant_locks(self) -> int:
        return 0

    async def append_tool_call_log(self, _record: object) -> None:
        pass


def _settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_ENVIRONMENT": "local",
            "GDS_DATABASE_DSN": "postgresql://unused@invalid.example.invalid/unused",
            "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_LOCAL_PRINCIPAL_OBJECT_ID": ("33333333-3333-3333-3333-333333333333"),
            "GDS_MCP_PUBLIC_URL": "https://testserver/mcp",
            "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": (
                "https://snapshot.blob.core.windows.net"
            ),
            "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
        }
    )


def _server() -> MCPServer[None]:
    settings = _settings()
    return create_mcp_server(
        settings,
        cast(Database, _SchemaDatabase()),
        IdentityProvider(settings.auth_mode),
    )


async def _list_tools() -> list[Tool]:
    async with Client(_server()) as client:
        return (await client.list_tools()).tools


def _model_description_server() -> MCPServer[None]:
    database = cast(Database, _SchemaDatabase())
    identity = IdentityProvider(AuthMode.DEV)
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="model-description-test")
    register_describe_model_dataset_tool(
        server,
        identity_provider=identity,
        audit=audit,
    )
    return server


@pytest.mark.asyncio
async def test_describe_metadata_dataset_advertises_the_exact_registry_enum() -> None:
    tools = {tool.name: tool for tool in await _list_tools()}
    schema = tools["describe_metadata_dataset"].input_schema

    assert schema["$defs"]["MetadataDataset"]["enum"] == list(DATASETS_BY_NAME)
    assert schema["properties"]["dataset"] == {"$ref": "#/$defs/MetadataDataset"}


@pytest.mark.asyncio
async def test_existing_model_tools_discover_code_and_qa_lifecycle_contracts() -> None:
    tools = {tool.name: tool for tool in await _list_tools()}
    expected = {"generated_code", "validation_group", "validation_check"}

    for tool_name in (
        "stage_model_change_set",
        "begin_model_stage_batch",
        "put_model_stage_chunk",
    ):
        advertised = set(
            tools[tool_name].input_schema["$defs"]["ModelChangeSetDataset"]["enum"]
        )
        assert expected <= advertised

    for tool_name in ("get_model_change_set", "describe_model_dataset"):
        advertised = set(tools[tool_name].input_schema["$defs"]["ModelDataset"]["enum"])
        assert advertised == set(MODEL_DATASETS_BY_NAME)

    code_output = tools["get_model_code_generation_document"].output_schema
    assert code_output is not None
    assert {
        "target_mapping_context_digest",
        "target_source_context_digest",
    } <= set(code_output["required"])
    assert (
        "canonical target"
        in tools["get_model_code_generation_document"].description.lower()
    )

    assert not expected & set(tools)


@pytest.mark.asyncio
async def test_model_stage_batch_tools_publish_additive_json_fragment_mode() -> None:
    tools = {tool.name: tool for tool in await _list_tools()}
    begin = tools["begin_model_stage_batch"].input_schema
    put = tools["put_model_stage_chunk"].input_schema

    assert begin["properties"]["payload_mode"]["default"] == "records"
    assert begin["properties"]["total_payload_bytes"]["anyOf"][0]["type"] == "integer"
    assert put["properties"]["payload_mode"]["default"] == "records"
    assert "payload_fragment_base64" in put["properties"]
    assert "records" not in put["required"]


@pytest.mark.parametrize("value", ["", "YQ", "YR==", "YQ==\n", "YQ==="])
def test_model_stage_payload_fragments_require_strict_canonical_base64(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="fragment is invalid"):
        decode_canonical_base64_fragment(value)

    assert decode_canonical_base64_fragment("YQ==") == b"a"


@pytest.mark.asyncio
async def test_describe_model_dataset_publishes_code_and_qa_authoring_rules() -> None:
    async with Client(_model_description_server()) as client:
        code = await client.call_tool(
            "describe_model_dataset",
            {"dataset": "generated_code", "detail": "full"},
        )
        qa_context = await client.call_tool(
            "describe_model_dataset",
            {"dataset": "qa_authoring_context", "detail": "full"},
        )
        group = await client.call_tool(
            "describe_model_dataset",
            {"dataset": "validation_group", "detail": "full"},
        )
        check = await client.call_tool(
            "describe_model_dataset",
            {"dataset": "validation_check", "detail": "full"},
        )

    assert code.is_error is False
    assert qa_context.is_error is False
    assert group.is_error is False
    assert check.is_error is False
    assert code.structured_content is not None
    assert qa_context.structured_content is not None
    assert group.structured_content is not None
    assert check.structured_content is not None

    code_schema = code.structured_content["record_schema"]
    assert (
        "x-gds-max-utf8-bytes"
        not in code_schema["properties"]["generated_code_content"]
    )
    code_digests = code_schema["x-gds-context-digest-contract"]
    assert code_digests["mapping_context_digest"]["result_field"] == (
        "target_mapping_context_digest"
    )
    assert code_digests["source_context_digest"]["result_field"] == (
        "target_source_context_digest"
    )
    assert code_schema["x-gds-apply-order"] == ["mapping", "generated_code"]

    assert qa_context.structured_content["change_set_eligible"] is False
    qa_context_schema = qa_context.structured_content["record_schema"]
    trusted = qa_context_schema["x-gds-trusted-context-contract"]
    assert trusted["server_derived"] is True
    assert trusted["snapshot_only"] is True
    assert trusted["current_code_join"]["reference_fields"] == [
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
        "modeled_entity_type",
        "artifact_type",
        "generated_code_digest",
    ]
    assert trusted["current_code_join"]["exclude_unreferenced_records"] is True
    assert any(
        "cannot be staged" in rule for rule in qa_context.structured_content["usage"]
    )

    group_schema = group.structured_content["record_schema"]
    assert group_schema["x-gds-apply-order"] == [
        "mapping",
        "current_relevant_generated_code_when_present",
        "qa",
    ]
    digest_contract = group_schema["x-gds-context-digest-contract"]
    assert digest_contract["trusted_snapshot_source"] == {
        "dataset": "qa_authoring_context",
        "join_fields": ["tenant_code", "system_code"],
        "copy_unchanged": True,
    }
    assert digest_contract["target_natural_key_normalization"] == {
        "applies_to": [
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        ],
        "operations_in_order": [
            "strip_leading_and_trailing_u+0020",
            "unicode_default_casefold",
        ],
    }
    assert digest_contract["mapping_context_digest"]["empty_result"] == (
        "invalid_applied_mapping_required"
    )
    assert digest_contract["code_context_digest"]["empty_result"] is None

    check_schema = check.structured_content["record_schema"]
    execution_shape = next(
        shape
        for shape in check_schema["x-gds-assertion-shapes"]
        if shape["operators"] == ["executes_successfully"]
    )
    assert execution_shape == {
        "operators": ["executes_successfully"],
        "result_data_types": [None],
        "comparison_query": "must_be_null",
        "comparison_value_types": ["none"],
        "comparison_value": "must_be_null",
        "query_a_must_return_rows": False,
        "query_a_result_cardinality": "ignored",
        "query_b_result_cardinality": "must_be_absent",
        "result_cell_type_field": None,
        "cardinality_mismatch_outcome": "not_applicable",
        "cardinality_mismatch_is_assertion_failure": False,
    }
    scalar_shape = next(
        shape
        for shape in check_schema["x-gds-assertion-shapes"]
        if shape["operators"] == ["equal", "not_equal"]
    )
    assert scalar_shape["query_a_result_cardinality"] == ("exactly_one_row_one_column")
    assert scalar_shape["query_b_result_cardinality"] == (
        "exactly_one_row_one_column_when_present"
    )
    assert scalar_shape["result_cell_type_field"] == ("validation_result_data_type")
    assert scalar_shape["cardinality_mismatch_outcome"] == (
        "query_contract_execution_error"
    )
    assert scalar_shape["cardinality_mismatch_is_assertion_failure"] is False
    for shape in check_schema["x-gds-assertion-shapes"]:
        if shape["operators"] == ["executes_successfully"]:
            continue
        assert shape["query_a_result_cardinality"] == ("exactly_one_row_one_column")
        assert shape["query_b_result_cardinality"] == (
            "exactly_one_row_one_column_when_present"
            if "query" in shape["comparison_value_types"]
            else "must_be_absent"
        )
        assert shape["result_cell_type_field"] == "validation_result_data_type"
        assert shape["cardinality_mismatch_outcome"] == (
            "query_contract_execution_error"
        )
        assert shape["cardinality_mismatch_is_assertion_failure"] is False
    assert check_schema["x-gds-sql-policy"]["apply_executes_sql"] is False
    assert check_schema["x-gds-sql-policy"]["physical_relations"] == (
        "require_catalog_schema_table"
    )
    query_column = next(
        column
        for column in check.structured_content["columns"]
        if column["name"] == "validation_query_sql"
    )
    assert "catalog.schema.table" in query_column["population_guidance"]
    assert "Query B" in " ".join(check.structured_content["usage"])


@pytest.mark.asyncio
async def test_describe_model_dataset_explains_every_registry_column() -> None:
    datasets = tuple(MODEL_DATASETS_BY_NAME)

    async with Client(_model_description_server()) as client:
        results = {
            dataset: await client.call_tool(
                "describe_model_dataset",
                {"dataset": dataset, "detail": "full"},
            )
            for dataset in datasets
        }

    for _dataset, result in results.items():
        assert result.is_error is False, _dataset
        assert result.structured_content is not None
        document = result.structured_content
        schema = document["record_schema"]
        assert document["population_rules"]
        columns = document["columns"]
        assert [column["name"] for column in columns] == list(schema["properties"])
        for column in columns:
            property_schema = schema["properties"][column["name"]]
            assert column["required"] is (column["name"] in schema["required"])
            assert isinstance(column["nullable"], bool)
            assert column["description"] == property_schema["description"]
            assert column["population_guidance"] == property_schema[
                "x-gds-population-guidance"
            ]
            assert column["description"].strip()
            assert column["population_guidance"].strip()
            assert column["accepted_values"]["kind"] in {
                "fixed",
                "literal",
                "reference",
                "constrained",
                "freeform",
            }
            assert isinstance(column["accepted_values"]["constraints"], dict)

    conceptual = {
        column["name"]: column
        for column in results["conceptual_object"].structured_content["columns"]
    }
    logical = {
        column["name"]: column
        for column in results["logical_entity"].structured_content["columns"]
    }
    dimensional = {
        column["name"]: column
        for column in results["dimensional_relationship"].structured_content[
            "columns"
        ]
    }
    assert "evidence" in conceptual["supports"]["population_guidance"].lower()
    assert "bronze" in logical["sources"]["population_guidance"].lower()
    assert "foreign key" in dimensional["dimensional_relationship_is_optional"][
        "description"
    ].lower()
    mapping = {
        column["name"]: column
        for column in results["mapping_object"].structured_content["columns"]
    }
    assert "target" in mapping["object_name"]["population_guidance"].lower()
    assert "all present or all null" in mapping["artifact_type"][
        "population_guidance"
    ].lower()
    package_constraints = mapping["mapping_package_document"]["accepted_values"][
        "constraints"
    ]
    assert package_constraints["x-gds-authoritative-validator"] == (
        "MappingPackageDocumentV1"
    )
    assert package_constraints["x-gds-governed-authoring-schema"]["required"]


@pytest.mark.asyncio
async def test_describe_model_dataset_defaults_to_a_bounded_authoring_contract() -> None:
    async with Client(_model_description_server()) as client:
        result = await client.call_tool(
            "describe_model_dataset",
            {"dataset": "mapping_object"},
        )

    assert result.is_error is False
    assert result.structured_content is not None
    document = result.structured_content
    assert document["detail"] == "compact"
    assert document["columns"] is None
    assert document["record_schema"] is None
    schema = document["authoring_schema"]
    encoded = json.dumps(schema, separators=(",", ":"))
    assert len(encoded.encode("utf-8")) < 20_000
    assert "x-gds-governed-authoring-schema" not in encoded
    assert "x-gds-columns" not in encoded
    assert schema["x-gds-population-rules"]
    assert schema["properties"]["mapping_package_document"]["x-gds-authoring-tool"] == (
        "validate_and_materialize_mapping_candidate"
    )


@pytest.mark.asyncio
async def test_every_advertised_tool_schema_is_valid_json_schema() -> None:
    for tool in await _list_tools():
        schemas = (("input", tool.input_schema), ("output", tool.output_schema))
        for schema_kind, schema in schemas:
            assert schema is not None, f"{tool.name} has no {schema_kind} schema"
            validator_for(schema).check_schema(schema)


@pytest.mark.asyncio
async def test_public_tool_schemas_exclude_web_application_contracts() -> None:
    forbidden_fragments = {
        "application.",
        "default_agent_",
        "generated_sql_artifact",
        "output_template_id",
        "prompt_assignment",
        "prompt_template",
        "prompt_version_id",
        "sql_generation_guide",
        "workflow_run_id",
    }

    for tool in await _list_tools():
        contract = json.dumps(
            {
                "input": tool.input_schema,
                "output": tool.output_schema,
            },
            sort_keys=True,
        ).lower()
        exposed = sorted(
            fragment for fragment in forbidden_fragments if fragment in contract
        )
        assert exposed == [], f"{tool.name} exposes web-only fields: {exposed}"


@pytest.mark.asyncio
async def test_execute_databricks_sql_requires_source_connection_environment_and_sql() -> (
    None
):
    tools = {tool.name: tool for tool in await _list_tools()}
    tool = tools["execute_databricks_sql"]

    assert set(tool.input_schema["required"]) == {
        "connection_id",
        "environment_code",
        "sql",
    }
    assert tool.input_schema["properties"]["environment_code"] == {
        "maxLength": 100,
        "minLength": 1,
        "title": "Environment Code",
        "type": "string",
    }
    assert tool.output_schema is not None
    assert "environment_code" in tool.output_schema["properties"]


@pytest.mark.asyncio
async def test_plugin_contract_fingerprint_matches_the_runtime() -> None:
    contract_path = (
        Path(__file__).resolve().parents[2]
        / "plugins"
        / "v2"
        / "gds"
        / "tool-contract.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    tools = await _list_tools()

    assert contract == {
        "schema_version": "1.0",
        "mcp_server_version": MCP_SERVER_VERSION,
        "tool_count": len(tools),
        "tool_contract_sha256": tool_contract_sha256(tools),
    }


@pytest.mark.asyncio
async def test_server_contract_tool_returns_its_complete_runtime_fingerprint() -> None:
    database = cast(Database, _SchemaDatabase())
    identity = IdentityProvider(AuthMode.DEV)
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="server-contract-test")
    register_server_contract_tool(
        server,
        identity_provider=identity,
        audit=audit,
        mcp_server_version=MCP_SERVER_VERSION,
        contract_digest=tool_contract_sha256,
    )
    async with Client(server) as client:
        listed = (await client.list_tools()).tools
        result = await client.call_tool("get_server_contract", {})

    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "mcp_server_version": MCP_SERVER_VERSION,
        "tool_count": len(listed),
        "tool_contract_sha256": tool_contract_sha256(listed),
    }


@pytest.mark.asyncio
async def test_change_set_prompts_are_parallel_and_bounded() -> None:
    async with Client(_server()) as client:
        listed = await client.list_prompts()
        metadata_result = await client.get_prompt(
            "work_with_metadata_change_set",
            {"tenant_id": "123"},
        )
        model_result = await client.get_prompt(
            "work_with_model_change_set",
            {"model_id": "123"},
        )

    prompt_names = {prompt.name for prompt in listed.prompts}
    assert prompt_names == {
        "work_with_metadata_change_set",
        "work_with_model_change_set",
    }

    metadata_content = metadata_result.messages[0].content
    assert metadata_content.type == "text"
    metadata_text = " ".join(metadata_content.text.split())
    assert "requested boundary" in metadata_text
    assert "Read-only inspection" in metadata_text
    assert "stop without a Snapshot or lock" in metadata_text
    assert "every dataset with a nonzero count" in metadata_text
    assert metadata_text.index(
        "ask before stage_metadata_change_set"
    ) < metadata_text.index(
        "fresh approval immediately before apply_metadata_change_set"
    )
    assert "archive needs no current lock" in metadata_text
    assert "Release any lock this workflow acquired when it stops" in metadata_text
    assert len(metadata_content.text.split()) <= 190

    content = model_result.messages[0].content
    assert content.type == "text"
    text = " ".join(content.text.split())
    assert "requested boundary" in text
    assert "Read-only inspection" in text
    assert "stop without a lock" in text
    assert (
        "If resumed, fetch the summary and every dataset with a nonzero count" in text
    )
    assert "Model Scope is read-only through MCP" in text
    stage_approval = text.index("ask before stage_model_change_set")
    apply_approval = text.index(
        "fresh approval immediately before apply_model_change_set"
    )
    assert stage_approval < apply_approval
    assert "Release any lock this workflow acquired when it stops" in text
    assert "archive needs no current lock" in text
    assert len(content.text.split()) <= 190


@pytest.mark.asyncio
async def test_mcp_has_no_public_resources() -> None:
    async with Client(_server()) as client:
        listed = await client.list_resources()

    assert listed.resources == []


def test_server_instructions_are_intent_bounded_and_compact() -> None:
    instructions = _server().instructions
    assert instructions is not None
    text = " ".join(instructions.split())
    assert "least-committed boundary" in text
    assert "Read-only Change Set inspection" in text
    assert "without a lock" in text
    assert "every nonempty pending dataset" in text
    assert text.index("Stage approval") < text.index("fresh Apply approval")
    assert "next_cursor" in text
    assert "archive needs no current lock" in text
    assert "execute_databricks_sql" in text
    assert len(instructions.split()) <= 170
