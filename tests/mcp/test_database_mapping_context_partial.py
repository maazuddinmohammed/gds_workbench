"""The governed MCP reader exposes partial applied Mapping without claiming completeness."""

# Fixture helpers create only disposable PostgreSQL contents.
# pyright: reportPrivateUsage=false
from uuid import uuid4

import pytest
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.tools.modeling.read_mapping_context import register_read_mapping_context_tool
from mcp import Client
from mcp.server.mcpserver import MCPServer

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import complete_model_graph
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _replace_codes,
    _seed_model_foundation,
)


@pytest.mark.parametrize("shape", ["object_only", "attribute_only", "partial", "empty"])
async def test_mcp_reader_keeps_partial_documents_and_completeness_signal(
    postgres_database: DisposablePostgres, shape: str
) -> None:
    prefix = "CONTEXT_PARTIAL_" + uuid4().hex
    model_id, tenant_id = _seed_model_foundation(postgres_database, code_prefix=prefix)
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE core.tenant SET tenant_catalog='fixture_catalog' WHERE tenant_id=%s",
            (tenant_id,),
        )
        connection.execute(
            "UPDATE core.object SET fc_object_schema=object_schema, fc_object_name=object_name "
            "WHERE source_tenant_id=%s",
            (tenant_id,),
        )
        connection.execute(
            "UPDATE core.attribute SET fc_attribute_name=attribute_name WHERE object_id IN "
            "(SELECT object_id FROM core.object WHERE source_tenant_id=%s)",
            (tenant_id,),
        )
    graph = _replace_codes(complete_model_graph(), code_prefix=prefix)
    graph["mapping_object"][0]["mapping_transformation_document"] = {
        "source_objects": None,
        "steps": ["Read the evidenced Order rows."],
    }
    for row in graph["mapping_attribute"]:
        row["attribute_mapping_transformation_document"] = {
            "source_attributes": None,
            "transformation": "Synthetic fixture expression.",
        }
    model = ModelReadContext(
        model_id=model_id, tenant_id=tenant_id, model_name="Model Tool Round Trip", model_revision=1
    )
    runtime = postgres_database.create_runtime_adapter()
    identity = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=runtime, identity_provider=identity, authorizer=authorizer
    )
    server = MCPServer[None](name="partial-mapping-reader", middleware=[audit])
    register_read_mapping_context_tool(
        server,
        database=runtime,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            snapshot = await build_model_snapshot(transaction, model)
            physical = await load_model_physical_scope(transaction, model)
            authored = validate_future_graph(
                snapshot=snapshot, staged_documents=graph, physical_scope=physical
            )
            assert authored.valid
            await ModelMaterializer(transaction, model_id, "a" * 64).apply(authored.records)
        request = {
            "model_id": model_id,
            "modeled_entity_type": "logical_entity",
            "modeled_entity_schema_name": "silver",
            "modeled_entity_name": "Order",
            "component": "attribute_transformations",
        }
        async with Client(server) as client:
            complete = await client.call_tool("read_mapping_context", request)
            assert not complete.is_error
            assert complete.structured_content is not None
            assert complete.structured_content["complete"]
            with postgres_database.connect_owner() as connection:
                if shape in {"attribute_only", "empty"}:
                    connection.execute(
                        "UPDATE workflow.mapping_object SET mapping_transformation_document=NULL "
                        "WHERE model_id=%s",
                        (model_id,),
                    )
                if shape in {"object_only", "partial", "empty"}:
                    connection.execute(
                        "UPDATE workflow.mapping_attribute "
                        "SET attribute_mapping_transformation_document=NULL "
                        "WHERE model_id=%s AND (%s <> 'partial' OR mapping_attribute_id=("
                        "SELECT min(mapping_attribute_id) FROM workflow.mapping_attribute "
                        "WHERE model_id=%s))",
                        (model_id, shape, model_id),
                    )
            partial = await client.call_tool("read_mapping_context", request)
            if shape == "empty":
                assert partial.is_error
                return
            assert not partial.is_error
            assert partial.structured_content is not None
            result = partial.structured_content
            assert not result["complete"]
            assert "mapping_document_not_canonical" in result["issues"]
            assert result["context_digest"] != complete.structured_content["context_digest"]
            assert len(result["records"]) == len(graph["mapping_attribute"])
            assert sum(row["transformation"] is not None for row in result["records"]) == (
                0 if shape == "object_only" else 1 if shape == "partial" else 2
            )
            objects = await client.call_tool(
                "read_mapping_context",
                {
                    **request,
                    "component": "object_transformations",
                    "expected_model_revision": result["model_revision"],
                    "expected_context_digest": result["context_digest"],
                },
            )
            assert not objects.is_error
            assert objects.structured_content is not None
            assert not objects.structured_content["complete"]
            assert (objects.structured_content["records"][0]["transformation"] is None) == (
                shape == "attribute_only"
            )
            changed = await client.call_tool(
                "read_mapping_context",
                {
                    **request,
                    "expected_context_digest": complete.structured_content["context_digest"],
                },
            )
            assert changed.is_error
    finally:
        await runtime.close()
