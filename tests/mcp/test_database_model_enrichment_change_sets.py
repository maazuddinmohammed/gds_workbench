"""Enrichment/settings round trip only through governed MCP on a disposable fixture."""

from typing import TYPE_CHECKING

import pytest
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.tools.change_sets.model import register_model_change_set_tools
from gds_etl_workbench.tools.modeling.read_model_section import register_read_model_section_tool
from mcp import Client
from mcp.server.mcpserver import MCPServer

from tests.mcp.model_test_fixtures import complete_model_graph
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _replace_codes,
    _seed_model_foundation,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres


@pytest.mark.parametrize("concurrent_edit", [False, True])
@pytest.mark.asyncio
async def test_model_enrichment_settings_round_trip_and_lock_fences(
    postgres_database: DisposablePostgres,
    concurrent_edit: bool,
) -> None:
    code_prefix = "ENRICH_EDIT" if concurrent_edit else "ENRICH_DRAFT"
    model_id, tenant_id = _seed_model_foundation(postgres_database, code_prefix=code_prefix)
    # Human-selected applied Input Scope is a prerequisite, never plugin-authored here.
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "INSERT INTO model.model_input_scope(model_id,object_id) "
            "SELECT %s, object.object_id FROM core.object AS object "
            "JOIN reference.zone USING(zone_id) "
            "WHERE source_tenant_id=%s AND zone_code IN ('source','bronze')",
            (model_id, tenant_id),
        )
    _acquire_tenant_lock(postgres_database, tenant_id)
    graph = _replace_codes(complete_model_graph(include_enrichment=True), code_prefix=code_prefix)
    details = graph["model_details"][0]
    details.update(
        logical_entity_scd_type="type_2",
        dimensional_entity_scd_type="type_1",
        default_mapping_source_system_code=f"{code_prefix}_ERP",
    )
    proposals = {
        name: graph[name]
        for name in (
            "model_details",
            "object_enrichment",
            "attribute_enrichment",
            "analysis_result",
        )
    }
    database = postgres_database.create_runtime_adapter()
    identity = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database, identity_provider=identity, authorizer=authorizer
    )
    server = MCPServer[None](name="enrichment-change-set-test", middleware=[audit])
    register_model_change_set_tools(
        server, database=database, identity_provider=identity, authorizer=authorizer, audit=audit
    )
    register_read_model_section_tool(
        server,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=b"synthetic-test-cursor-signing-key-32",
    )
    await database.open()
    try:
        async with Client(server) as client:
            # Test both new findings and edits to existing Object + Attribute findings together.
            for iteration in range(2):
                if iteration:
                    proposals["object_enrichment"][0]["object_description"] = (
                        "Revised customer orders."
                    )
                    proposals["attribute_enrichment"][0]["attribute_description"] = (
                        "Revised order identifier."
                    )
                created = await client.call_tool("create_model_change_set", {"model_id": model_id})
                assert not created.is_error
                change_set_id = created.structured_content["model_change_set_id"]
                stage = await client.call_tool(
                    "stage_model_change_set",
                    {
                        "model_id": model_id,
                        "model_change_set_id": change_set_id,
                        "expected_draft_revision": 1,
                        "changes": [
                            {"dataset": name, "records": records}
                            for name, records in proposals.items()
                        ],
                    },
                )
                assert not stage.is_error
                validated = await client.call_tool(
                    "validate_model_change_set",
                    {
                        "model_id": model_id,
                        "model_change_set_id": change_set_id,
                        "expected_draft_revision": 2,
                    },
                )
                assert not validated.is_error
                assert validated.structured_content["valid"], [
                    (error["code"], error["fields"])
                    for error in validated.structured_content["errors"]
                ]
                applied = await client.call_tool(
                    "apply_model_change_set",
                    {
                        "model_id": model_id,
                        "model_change_set_id": change_set_id,
                        "expected_draft_revision": 2,
                    },
                )
                assert not applied.is_error
                for dataset in ("object_enrichment", "attribute_enrichment"):
                    read = await client.call_tool(
                        "read_model_section", {"model_id": model_id, "dataset": dataset}
                    )
                    assert not read.is_error
                    saved = read.structured_content["records"]
                    assert [
                        {k: v for k, v in row.items() if k != "expected_revision"} for row in saved
                    ] == [
                        {k: v for k, v in row.items() if k != "expected_revision"}
                        for row in proposals[dataset]
                    ]
                    assert all(len(row["expected_revision"]) == 64 for row in saved)
                    proposals[dataset] = saved
            with postgres_database.connect_owner() as connection:
                row = connection.execute(
                    "SELECT model_name, logical_entity_scd_type, dimensional_entity_scd_type, "
                    "system_code FROM model.model LEFT JOIN core.system ON "
                    "system_id=default_mapping_source_system_id WHERE model_id=%s",
                    (model_id,),
                ).fetchone()
                assert row == {
                    "model_name": "Model Tool Round Trip",
                    "logical_entity_scd_type": "type_2",
                    "dimensional_entity_scd_type": "type_1",
                    "system_code": f"{code_prefix}_ERP",
                }
                assert connection.execute(
                    "SELECT count(*) AS n FROM core.object WHERE source_tenant_id=%s "
                    "AND object_description IS NOT NULL",
                    (tenant_id,),
                ).fetchone() == {"n": 0}
                # Human lock protects the Object and its Attributes on subsequent drafts.
                if not concurrent_edit:
                    connection.execute(
                        "UPDATE workflow.object_enrichment SET is_locked=TRUE WHERE model_id=%s",
                        (model_id,),
                    )
                assert connection.execute(
                    "SELECT has_table_privilege('gds_app_write',"
                    "'workflow.attribute_enrichment','INSERT,UPDATE') AS writable"
                ).fetchone() == {"writable": False}
            created = await client.call_tool("create_model_change_set", {"model_id": model_id})
            assert not created.is_error
            protected_id = created.structured_content["model_change_set_id"]
            changed = {**proposals["attribute_enrichment"][0], "is_pii": True}
            staged = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": protected_id,
                    "expected_draft_revision": 1,
                    "changes": [{"dataset": "attribute_enrichment", "records": [changed]}],
                },
            )
            assert not staged.is_error, [
                code
                for code in (
                    "internal_error",
                    "dependency_unavailable",
                    "draft_revision_conflict",
                    "model_change_set_not_active",
                    "invalid_request",
                    "record_locked",
                    "tenant_lock_required",
                    "tenant_locked",
                )
                if any(code in getattr(content, "text", "") for content in staged.content)
            ]
            rejected = await client.call_tool(
                "validate_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": protected_id,
                    "expected_draft_revision": 2,
                },
            )
            assert not rejected.is_error
            if concurrent_edit:
                assert rejected.structured_content["valid"]
                # A newer human finding must survive Apply, even without a Model revision change.
                with postgres_database.connect_owner() as connection:
                    connection.execute(
                        "UPDATE workflow.attribute_enrichment "
                        "SET attribute_description='Human review' WHERE model_id=%s",
                        (model_id,),
                    )
                conflict = await client.call_tool(
                    "apply_model_change_set",
                    {
                        "model_id": model_id,
                        "model_change_set_id": protected_id,
                        "expected_draft_revision": 2,
                    },
                )
                assert conflict.is_error
                with postgres_database.connect_owner() as connection:
                    assert connection.execute(
                        "SELECT bool_and(attribute_description='Human review') AS preserved "
                        "FROM workflow.attribute_enrichment WHERE model_id=%s",
                        (model_id,),
                    ).fetchone() == {"preserved": True}
                return
            assert not rejected.structured_content["valid"]
            assert any(
                error["code"] == "enrichment_parent_locked"
                for error in rejected.structured_content["errors"]
            )
    finally:
        await database.close()
