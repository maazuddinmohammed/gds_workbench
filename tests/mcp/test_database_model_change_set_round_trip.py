from __future__ import annotations

import io
import json
import zipfile
from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from test_model_change_set_validation import _complete_graph

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.tools.change_sets.model import register_model_change_set_tools
from gds_etl_workbench.tools.modeling.assertions import (
    register_modeling_assertion_tools,
)
from gds_etl_workbench.tools.modeling.conceptual import register_conceptual_tools
from gds_etl_workbench.tools.modeling.dimensional import register_dimensional_tools
from gds_etl_workbench.tools.modeling.logical import register_logical_tools
from gds_etl_workbench.tools.modeling.mapping import register_mapping_tools
from gds_etl_workbench.tools.modeling.model_details import register_get_model_tool
from gds_etl_workbench.tools.modeling.model_scope import register_get_model_scope_tool
from gds_etl_workbench.tools.modeling.profiling_analysis import (
    register_profiling_analysis_tools,
)
from gds_etl_workbench.tools.snapshots.archive import SnapshotArchive
from gds_etl_workbench.tools.snapshots.dbml.get_model_dbml import (
    register_get_model_dbml_tool,
)
from gds_etl_workbench.tools.snapshots.model.contracts import DATASETS
from gds_etl_workbench.tools.snapshots.model.get_model_snapshot import (
    register_get_model_snapshot_tool,
)
from gds_etl_workbench.tools.snapshots.storage import SnapshotKind

if TYPE_CHECKING:
    from conftest import DisposablePostgres

ENTRA_TENANT_ID = UUID("10000000-0000-4000-8000-000000000071")
ENTRA_OBJECT_ID = UUID("20000000-0000-4000-8000-000000000071")


class StaticIdentityProvider(IdentityProvider):
    def __init__(self) -> None:
        super().__init__(AuthMode.DEV)

    def request_principal(self, request: object | None) -> RequestPrincipal:
        del request
        return RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=ENTRA_TENANT_ID,
            entra_object_id=ENTRA_OBJECT_ID,
        )


class RecordingSnapshotStore:
    def __init__(self) -> None:
        self.archive_content: dict[SnapshotKind, bytes] = {}

    async def close(self) -> None:
        return None

    async def upload_archive(
        self,
        archive: SnapshotArchive,
        *,
        snapshot_kind: SnapshotKind,
        scope_id: int,
        schema_version: str,
        snapshot_id: UUID,
        created_at: datetime,
        available_until: datetime,
    ) -> None:
        assert snapshot_kind in {"model", "dbml"}
        assert scope_id > 0
        assert schema_version == "2.0"
        assert snapshot_id.version == 4
        assert available_until > created_at
        self.archive_content[snapshot_kind] = archive.path.read_bytes()

    async def create_read_url(
        self,
        *,
        snapshot_kind: SnapshotKind,
        scope_id: int,
        schema_version: str,
        snapshot_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> str | None:
        del scope_id, snapshot_id, now, ttl_seconds
        assert snapshot_kind in {"model", "dbml"}
        assert schema_version == "2.0"
        return f"https://snapshot.example.test/{snapshot_kind}.zip?read-only"


@pytest.mark.asyncio
async def test_all_model_datasets_materialize_and_round_trip_as_one_snapshot(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(postgres_database)
    staged = _replace_codes(_complete_graph())
    _acquire_tenant_lock(postgres_database, tenant_id)

    database = postgres_database.create_runtime_adapter()
    identity_provider = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    snapshot_store = RecordingSnapshotStore()
    server = MCPServer[None](name="model-change-set-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    register_get_model_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    register_get_model_scope_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    register_get_model_snapshot_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        store=snapshot_store,
        download_ttl_seconds=300,
        retention_hours=24,
        max_archive_bytes=16 * 1024 * 1024,
    )
    register_get_model_dbml_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        store=snapshot_store,
        download_ttl_seconds=300,
        retention_hours=24,
        max_archive_bytes=16 * 1024 * 1024,
    )
    for register in (
        register_profiling_analysis_tools,
        register_modeling_assertion_tools,
        register_conceptual_tools,
        register_logical_tools,
        register_dimensional_tools,
        register_mapping_tools,
    ):
        register(
            server,
            database=database,
            identity_provider=identity_provider,
            authorizer=authorizer,
            audit=audit,
            cursor_signing_key=b"development-only-key-32-bytes-long",
        )
    await database.open()
    try:
        async with Client(server) as client:
            model_details = await client.call_tool(
                "get_model",
                {"tenant_id": tenant_id},
            )
            assert model_details.is_error is False
            returned_model = next(
                model
                for model in model_details.structured_content["models"]
                if model["model_id"] == model_id
            )
            assert returned_model["model_name"] == "Model Tool Round Trip"
            assert returned_model["model_scope_object_count"] == 2
            initial_scope = await client.call_tool(
                "get_model_scope",
                {"model_id": model_id},
            )
            assert initial_scope.is_error is False
            assert initial_scope.structured_content["object_count"] == 2
            created = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert created.is_error is False
            change_set_id = created.structured_content["model_change_set_id"]
            staged_result = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 1,
                    "changes": [
                        {"dataset": dataset, "records": records}
                        for dataset, records in staged.items()
                    ],
                },
            )
            assert staged_result.is_error is False
            draft_revision = staged_result.structured_content["draft_revision"]
            pending = await client.call_tool(
                "get_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "dataset": "logical_entity",
                },
            )
            assert pending.is_error is False
            assert len(pending.structured_content["records"]) == 2
            validated = await client.call_tool(
                "validate_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": draft_revision,
                },
            )
            assert validated.is_error is False
            assert validated.structured_content["valid"] is True
            assert validated.structured_content["phase"] == "complete"
            assert len(validated.structured_content["action_review"]) == 19
            applied = await client.call_tool(
                "apply_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": draft_revision,
                },
            )
            assert applied.is_error is False
            action_count = applied.structured_content["action_count"]
            snapshot_result = await client.call_tool(
                "get_model_snapshot",
                {"model_id": model_id},
            )
            assert snapshot_result.is_error is False
            descriptor = snapshot_result.structured_content
            assert descriptor["schema_version"] == "2.0"
            assert descriptor["snapshot_kind"] == "model"
            assert descriptor["status"] == "ready"
            assert descriptor["model_id"] == model_id
            assert descriptor["model_revision"] == 2
            assert descriptor["content_type"] == "application/zip"
            snapshot_counts, serialized = _snapshot_archive(
                snapshot_store.archive_content["model"]
            )
            dbml_result = await client.call_tool(
                "get_model_dbml",
                {
                    "model_id": model_id,
                    "model_type": "full",
                    "include_submodels": True,
                },
            )
            assert dbml_result.is_error is False
            dbml_descriptor = dbml_result.structured_content
            assert dbml_descriptor["snapshot_kind"] == "dbml"
            assert dbml_descriptor["model_revision"] == 2
            assert dbml_descriptor["model_type"] == "full"
            assert dbml_descriptor["include_submodels"] is True
            assert dbml_descriptor["dbml_file_count"] == 5
            _assert_dbml_archive(snapshot_store.archive_content["dbml"])
            await _assert_focused_reads(client, model_id)
            scope_archive = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert scope_archive.is_error is False
            archived_scope_record = deepcopy(staged["model_scope"][0])
            archived_scope_record["is_active"] = False
            archived_scope_stage = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": scope_archive.structured_content[
                        "model_change_set_id"
                    ],
                    "expected_draft_revision": 1,
                    "changes": [
                        {"dataset": "model_scope", "records": [archived_scope_record]}
                    ],
                },
            )
            assert archived_scope_stage.is_error is False
            archived_scope_validation = await client.call_tool(
                "validate_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": scope_archive.structured_content[
                        "model_change_set_id"
                    ],
                    "expected_draft_revision": 2,
                },
            )
            assert archived_scope_validation.is_error is False
            assert archived_scope_validation.structured_content["valid"] is True
            assert archived_scope_validation.structured_content["action_review"][0][
                "deactivate_count"
            ] == 1
            archived_scope_apply = await client.call_tool(
                "apply_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": scope_archive.structured_content[
                        "model_change_set_id"
                    ],
                    "expected_draft_revision": 2,
                },
            )
            assert archived_scope_apply.is_error is False
            active_scope = await client.call_tool(
                "get_model_scope",
                {"model_id": model_id},
            )
            assert active_scope.is_error is False
            assert active_scope.structured_content["object_count"] == 1
            assert all(
                item["object_name"] != archived_scope_record["object_name"]
                for item in active_scope.structured_content["objects"]
            )
            active_model = await client.call_tool("get_model", {"tenant_id": tenant_id})
            assert active_model.is_error is False
            current_model = next(
                item
                for item in active_model.structured_content["models"]
                if item["model_id"] == model_id
            )
            assert current_model["model_scope_object_count"] == 1
            archived_snapshot = await client.call_tool(
                "get_model_snapshot",
                {"model_id": model_id},
            )
            assert archived_snapshot.is_error is False
            assert archived_snapshot.structured_content["model_revision"] == 3
            archived_counts, archived_serialized = _snapshot_archive(
                snapshot_store.archive_content["model"]
            )
            assert archived_counts["model_scope"] == 1
            assert archived_counts["profiling_profile"] == 0
            assert archived_counts["analysis_result"] == 0
            assert archived_counts["mapping_object"] == 0
            assert archived_counts["mapping_attribute"] == 0
            assert '"object_name":"orders"' not in archived_serialized
            abandoned = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert abandoned.is_error is False
            abandoned_id = abandoned.structured_content["model_change_set_id"]
            archived = await client.call_tool(
                "archive_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": abandoned_id,
                    "expected_draft_revision": 1,
                },
            )
            assert archived.is_error is False
            assert archived.structured_content["status"] == "archived"
            retained = await client.call_tool(
                "get_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": abandoned_id,
                },
            )
            assert retained.is_error is False
            assert retained.structured_content["status"] == "discarded"
            assert retained.structured_content["terminal_at"] is not None
            invalid_scope = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert invalid_scope.is_error is False
            invalid_scope_id = invalid_scope.structured_content["model_change_set_id"]
            outside_profile = deepcopy(staged["profiling_profile"][0])
            outside_profile["object_name"] = "outside_scope"
            outside_stage = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": invalid_scope_id,
                    "expected_draft_revision": 1,
                    "changes": [
                        {"dataset": "profiling_profile", "records": [outside_profile]}
                    ],
                },
            )
            assert outside_stage.is_error is False
            outside_validation = await client.call_tool(
                "validate_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": invalid_scope_id,
                    "expected_draft_revision": 2,
                },
            )
            assert outside_validation.is_error is False
            assert outside_validation.structured_content["valid"] is False
            assert outside_validation.structured_content["phase"] == "model_scope"
    finally:
        await database.close()

    assert action_count == 36
    assert snapshot_counts == {
        "model_details": 1,
        "model_scope": 2,
        "profiling_profile": 1,
        "analysis_result": 1,
        "modeling_assertion_document": 1,
        "modeling_assertion_record": 1,
        "conceptual_object": 2,
        "conceptual_relationship": 1,
        "logical_submodel": 1,
        "logical_entity": 2,
        "logical_attribute": 2,
        "logical_relationship": 1,
        "dimensional_submodel": 1,
        "dimensional_entity": 2,
        "dimensional_attribute": 2,
        "dimensional_relationship": 1,
        "mapping_dependency": 1,
        "mapping_object": 1,
        "mapping_attribute": 1,
    }
    for forbidden in (
        "agent_run_id",
        "created_by",
        "created_time",
        "updated_by",
        "updated_time",
        "source_context_digest",
        "analysis_result_id",
    ):
        assert forbidden not in serialized


def _seed_model_foundation(postgres_database: DisposablePostgres) -> tuple[int, int]:
    with postgres_database.connect_owner() as connection:
        system_type_id = _required_id(
            connection.execute(
                """
            INSERT INTO reference.system_type (system_type_code, system_type_name)
            VALUES ('MODEL_TOOL_DATABASE', 'Model Tool Database')
            RETURNING system_type_id
            """
            ).fetchone(),
            "system_type_id",
        )
        connection_type_id = _required_id(
            connection.execute(
                """
            INSERT INTO reference.connection_type (
                connection_type_code,
                connection_type_name
            )
            VALUES ('MODEL_TOOL_POSTGRES', 'Model Tool Postgres')
            RETURNING connection_type_id
            """
            ).fetchone(),
            "connection_type_id",
        )
        object_type_id = _required_id(
            connection.execute(
                """
            INSERT INTO reference.object_type (object_type_code, object_type_name)
            VALUES ('MODEL_TOOL_TABLE', 'Model Tool Table')
            RETURNING object_type_id
            """
            ).fetchone(),
            "object_type_id",
        )
        zone_id = _required_id(
            connection.execute(
                """
            INSERT INTO reference.zone (zone_code, zone_name)
            VALUES ('model_tool_raw', 'Model Tool Raw')
            RETURNING zone_id
            """
            ).fetchone(),
            "zone_id",
        )
        project_id = _required_id(
            connection.execute(
                """
            INSERT INTO core.project (project_code, project_name)
            VALUES ('MODEL_TOOL_PROJECT', 'Model Tool Project')
            RETURNING project_id
            """
            ).fetchone(),
            "project_id",
        )
        tenant_id = _required_id(
            connection.execute(
                """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog
            )
            VALUES (%s, 'MODEL_TOOL_TENANT', 'Model Tool Tenant', 'model_tool', 'model_tool_admin')
            RETURNING tenant_id
            """,
                (project_id,),
            ).fetchone(),
            "tenant_id",
        )
        system_id = _required_id(
            connection.execute(
                """
            INSERT INTO core.system (
                system_code,
                system_name,
                system_type_id
            )
            VALUES ('MODEL_TOOL_ERP', 'Model Tool ERP', %s)
            RETURNING system_id
            """,
                (system_type_id,),
            ).fetchone(),
            "system_id",
        )
        connection_id = _required_id(
            connection.execute(
                """
            INSERT INTO core.connection (
                tenant_id,
                system_id,
                connection_code,
                connection_name,
                connection_type_id
            )
            VALUES (%s, %s, 'MODEL_TOOL_SOURCE', 'Model Tool Source', %s)
            RETURNING connection_id
            """,
                (tenant_id, system_id, connection_type_id),
            ).fetchone(),
            "connection_id",
        )
        object_ids = []
        for object_name in ("orders", "customers"):
            object_id = _required_id(
                connection.execute(
                    """
                INSERT INTO core.object (
                    connection_id,
                    object_schema,
                    object_name,
                    object_type_id,
                    zone_id
                )
                VALUES (%s, 'sales', %s, %s, %s)
                RETURNING object_id
                """,
                    (connection_id, object_name, object_type_id, zone_id),
                ).fetchone(),
                "object_id",
            )
            connection.execute(
                """
                INSERT INTO core.attribute (
                    object_id,
                    attribute_name,
                    attribute_ordinal_position,
                    attribute_data_type,
                    attribute_nullability
                )
                VALUES (%s, 'customer_id', 1, 'bigint', FALSE)
                """,
                (object_id,),
            )
            object_ids.append(object_id)
        model_id = _required_id(
            connection.execute(
                """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, 'Model Tool Round Trip')
            RETURNING model_id
            """,
                (tenant_id,),
            ).fetchone(),
            "model_id",
        )
        for object_id in object_ids:
            connection.execute(
                """
                INSERT INTO model.model_scope (model_id, object_id)
                VALUES (%s, %s)
                """,
                (model_id, object_id),
            )
        principal_id = _required_id(
            connection.execute(
                """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            )
            VALUES ('user', 'Model Tool Developer', 'model-tool@example.test')
            RETURNING principal_id
            """
            ).fetchone(),
            "principal_id",
        )
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            )
            VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, ENTRA_TENANT_ID, ENTRA_OBJECT_ID),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            )
            VALUES (%s, %s, 'architect', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
    return model_id, tenant_id


def _required_id(row: dict[str, Any] | None, field: str) -> int:
    assert row is not None
    value = row[field]
    assert type(value) is int
    return value


def _acquire_tenant_lock(
    postgres_database: DisposablePostgres,
    tenant_id: int,
) -> None:
    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT,
                  60::INTEGER,
                  'Model change set test'::VARCHAR
              )
            """,
            (ENTRA_TENANT_ID, ENTRA_OBJECT_ID, tenant_id),
        ).fetchone()
    assert result == {"acquired": True}


def _replace_codes(value: Any) -> Any:
    replacements = {
        "DEMO": "MODEL_TOOL_TENANT",
        "ERP": "MODEL_TOOL_ERP",
        "SOURCE": "MODEL_TOOL_SOURCE",
    }
    if isinstance(value, dict):
        return {key: _replace_codes(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_codes(item) for item in value]
    return replacements.get(value, value)


def _snapshot_archive(content: bytes) -> tuple[dict[str, int], str]:
    assert content
    counts: dict[str, int] = {}
    serialized: list[str] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        manifest = json.loads(archive.read("model-snapshot/manifest.json"))
        assert manifest["snapshot_kind"] == "model"
        assert manifest["database_ids_included"] is False
        for definition in DATASETS:
            rows = archive.read(f"model-snapshot/{definition.rows_path}").decode("utf-8")
            counts[definition.name] = len(rows.splitlines())
            serialized.append(rows)
    return counts, "".join(serialized)


def _assert_dbml_archive(content: bytes) -> None:
    assert content
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert archive.namelist() == [
            "model-dbml/manifest.json",
            "model-dbml/files/conceptual.dbml",
            "model-dbml/files/dimensional_complete.dbml",
            "model-dbml/files/dimensional_sales_mart.dbml",
            "model-dbml/files/logical_complete.dbml",
            "model-dbml/files/logical_sales.dbml",
        ]
        manifest = json.loads(archive.read("model-dbml/manifest.json"))
        assert manifest["snapshot_kind"] == "dbml"
        assert manifest["counts"]["dbml_file_count"] == 5
        logical = archive.read("model-dbml/files/logical_complete.dbml").decode()
        dimensional = archive.read(
            "model-dbml/files/dimensional_complete.dbml"
        ).decode()
        assert 'Table "Order"' in logical
        assert "Ref logical_relationship_1:" in logical
        assert 'Table "Sales Fact"' in dimensional
        assert "Ref dimensional_relationship_1:" in dimensional


async def _assert_focused_reads(client: Client, model_id: int) -> None:
    expected = (
        ("get_model_profiling", "profiles", 1),
        ("get_modeling_assertion_documents", "documents", 1),
        ("get_modeling_assertion_records", "records", 1),
        ("get_model_conceptual_objects", "objects", 2),
        ("get_model_conceptual_relationships", "relationships", 1),
        ("get_model_logical_submodels", "submodels", 1),
        ("get_model_logical_entities", "entities", 2),
        ("get_model_logical_attributes", "attributes", 2),
        ("get_model_logical_relationships", "relationships", 1),
        ("get_model_dimensional_submodels", "submodels", 1),
        ("get_model_dimensional_entities", "entities", 2),
        ("get_model_dimensional_attributes", "attributes", 2),
        ("get_model_dimensional_relationships", "relationships", 1),
        ("get_model_mapping_dependencies", "dependencies", 1),
        ("get_model_object_mappings", "mappings", 1),
        ("get_model_attribute_mappings", "mappings", 1),
    )
    contents: dict[str, dict[str, Any]] = {}
    for tool_name, collection, count in expected:
        result = await client.call_tool(tool_name, {"model_id": model_id})
        assert result.is_error is False, tool_name
        assert result.structured_content is not None
        contents[tool_name] = result.structured_content
        assert len(result.structured_content[collection]) == count

    analysis = await client.call_tool("get_model_analysis", {"model_id": model_id})
    assert analysis.is_error is False
    assert analysis.structured_content is not None
    assert len(analysis.structured_content["from_relationships"]) == 1
    assert len(analysis.structured_content["to_relationships"]) == 1

    object_id = contents["get_model_profiling"]["profiles"][0]["object_id"]
    assertion_document_id = contents["get_modeling_assertion_documents"]["documents"][
        0
    ]["modeling_assertion_document_id"]
    conceptual_object_id = contents["get_model_conceptual_objects"]["objects"][0][
        "conceptual_object_id"
    ]
    logical_entity_id = next(
        entity["logical_entity_id"]
        for entity in contents["get_model_logical_entities"]["entities"]
        if entity["logical_entity_name"] == "Order"
    )
    dimensional_entity_id = next(
        entity["dimensional_entity_id"]
        for entity in contents["get_model_dimensional_entities"]["entities"]
        if entity["dimensional_entity_name"] == "Sales Fact"
    )

    filtered_reads = (
        ("get_model_profiling", {"object_ids": [object_id]}, "profiles"),
        (
            "get_modeling_assertion_records",
            {"modeling_assertion_document_ids": [assertion_document_id]},
            "records",
        ),
        (
            "get_model_conceptual_objects",
            {"supporting_object_ids": [object_id]},
            "objects",
        ),
        (
            "get_model_conceptual_relationships",
            {"conceptual_object_ids": [conceptual_object_id]},
            "relationships",
        ),
        (
            "get_model_logical_entities",
            {"supporting_object_ids": [object_id]},
            "entities",
        ),
        (
            "get_model_logical_attributes",
            {"logical_entity_ids": [logical_entity_id]},
            "attributes",
        ),
        (
            "get_model_logical_relationships",
            {"logical_entity_ids": [logical_entity_id]},
            "relationships",
        ),
        (
            "get_model_dimensional_entities",
            {"supporting_object_ids": [object_id]},
            "entities",
        ),
        (
            "get_model_dimensional_attributes",
            {"dimensional_entity_ids": [dimensional_entity_id]},
            "attributes",
        ),
        (
            "get_model_dimensional_relationships",
            {"dimensional_entity_ids": [dimensional_entity_id]},
            "relationships",
        ),
        ("get_model_object_mappings", {"object_ids": [object_id]}, "mappings"),
        ("get_model_attribute_mappings", {"object_ids": [object_id]}, "mappings"),
    )
    for tool_name, filters, collection in filtered_reads:
        result = await client.call_tool(
            tool_name,
            {"model_id": model_id, **filters},
        )
        assert result.is_error is False, tool_name
        assert result.structured_content is not None
        assert len(result.structured_content[collection]) == 1

    filtered_analysis = await client.call_tool(
        "get_model_analysis",
        {"model_id": model_id, "object_ids": [object_id]},
    )
    assert filtered_analysis.is_error is False
    assert filtered_analysis.structured_content is not None
    assert len(filtered_analysis.structured_content["from_relationships"]) == 1
    assert len(filtered_analysis.structured_content["to_relationships"]) == 0
