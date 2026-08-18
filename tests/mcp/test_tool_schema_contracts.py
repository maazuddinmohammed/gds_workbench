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
from gds_etl_workbench.configuration import RuntimeSettings
from gds_etl_workbench.infrastructure.postgres import Database
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS_BY_NAME


class _SchemaDatabase:
    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def expire_tenant_locks(self) -> int:
        return 0


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


@pytest.mark.asyncio
async def test_describe_metadata_dataset_advertises_the_exact_registry_enum() -> None:
    tools = {tool.name: tool for tool in await _list_tools()}
    schema = tools["describe_metadata_dataset"].input_schema

    assert schema["$defs"]["MetadataDataset"]["enum"] == list(DATASETS_BY_NAME)
    assert schema["properties"]["dataset"] == {"$ref": "#/$defs/MetadataDataset"}


@pytest.mark.asyncio
async def test_every_advertised_tool_schema_is_valid_json_schema() -> None:
    for tool in await _list_tools():
        schemas = (("input", tool.input_schema), ("output", tool.output_schema))
        for schema_kind, schema in schemas:
            assert schema is not None, f"{tool.name} has no {schema_kind} schema"
            validator_for(schema).check_schema(schema)


@pytest.mark.asyncio
async def test_plugin_contract_fingerprint_matches_the_runtime() -> None:
    contract_path = (
        Path(__file__).resolve().parents[2] / "plugins" / "gds" / "tool-contract.json"
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
    assert {
        "work_with_metadata_change_set",
        "work_with_model_change_set",
    } <= prompt_names

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
    stage_approval = text.index("ask before stage_model_change_set")
    apply_approval = text.index(
        "fresh approval immediately before apply_model_change_set"
    )
    assert stage_approval < apply_approval
    assert "Release any lock this workflow acquired when it stops" in text
    assert "archive needs no current lock" in text
    assert len(content.text.split()) <= 190


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
