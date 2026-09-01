from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import zipfile
from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast, overload
from uuid import UUID

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import TextContent
from psycopg import sql
from psycopg.types.json import Jsonb
from tests.mcp.test_model_change_set_validation import (
    complete_graph,
    model_scope_records,
)

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.modeling_records import (
    ANALYSIS_VALIDATION_FIELDS,
    GeneratedCodeRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.tools.change_sets.model import (
    _DATABASE_TIME_SQL,
    _EXPIRE_OWNED_SQL,
    _LOCK_OWNED_CHANGE_SETS_SQL,
    _STAGE_SQL,
    _TOUCH_MODEL_STAGE_BATCH_SQL,
    WRITE_SECTION_COLUMNS,
    register_model_change_set_tools,
)
from gds_etl_workbench.tools.change_sets.common import (
    MAX_MODEL_STAGE_CHUNK_BYTES,
    canonical_records_sha256,
    stage_batch_sha256,
)
from gds_etl_workbench.tools.change_sets.model_validation import (
    CodeGenerationTargetContext,
    qa_code_context_digest,
    qa_mapping_context_digest,
)
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
from gds_etl_workbench.tools.snapshots.model.contracts import (
    DATASETS,
    ModelChangeSetDataset,
)
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


def test_model_change_set_expiry_preserves_the_last_valid_activity_time(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, _ = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_EXPIRY",
    )
    change_set_id = UUID("30000000-0000-4000-8000-000000000071")
    correlation_id = UUID("40000000-0000-4000-8000-000000000071")
    with postgres_database.connect_owner() as connection:
        principal = connection.execute(
            """
            SELECT principal.principal_id
              FROM security.entra_principal_identity AS identity
              JOIN security.principal AS principal
                ON principal.principal_id = identity.principal_id
             WHERE identity.entra_tenant_id = %s
               AND identity.entra_object_id = %s
            """,
            (ENTRA_TENANT_ID, ENTRA_OBJECT_ID),
        ).fetchone()
        assert principal is not None
        connection.execute(
            """
            INSERT INTO mcp.model_change_set (
                model_change_set_id,
                model_id,
                base_model_revision,
                base_source_context_digest,
                base_assertion_digest,
                base_policy_digest,
                created_by_principal_id,
                correlation_id,
                created_time,
                last_activity_time,
                expires_time
            ) VALUES (
                %s, %s, 1, %s, %s, %s, %s, %s,
                clock_timestamp() - INTERVAL '3 hours',
                clock_timestamp() - INTERVAL '2 hours',
                clock_timestamp() - INTERVAL '1 hour'
            )
            """,
            (
                change_set_id,
                model_id,
                "a" * 64,
                "b" * 64,
                "c" * 64,
                principal["principal_id"],
                correlation_id,
            ),
        )

    with postgres_database.connect_runtime() as connection:
        connection.execute(
            _LOCK_OWNED_CHANGE_SETS_SQL,
            (model_id, principal["principal_id"]),
        ).fetchall()
        operation_time = connection.execute(_DATABASE_TIME_SQL).fetchone()
        assert operation_time is not None
        expired = connection.execute(
            _EXPIRE_OWNED_SQL,
            (operation_time["current_time"], model_id, principal["principal_id"]),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT model_change_set_status,
                   last_activity_time < expires_time AS activity_precedes_expiry,
                   terminal_time IS NOT NULL AS terminal
              FROM mcp.model_change_set
             WHERE model_change_set_id = %s
            """,
            (change_set_id,),
        ).fetchone()

    assert expired == {
        "model_change_set_id": change_set_id,
        "draft_revision": 1,
    }
    assert stored == {
        "model_change_set_status": "expired",
        "activity_precedes_expiry": True,
        "terminal": True,
    }


def test_expired_model_stage_batch_touch_is_a_safe_no_op(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, _ = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_BATCH_TOUCH",
    )
    change_set_id = UUID("30000000-0000-4000-8000-000000000072")
    stage_batch_id = UUID("40000000-0000-4000-8000-000000000072")
    with postgres_database.connect_owner() as connection:
        principal = connection.execute(
            """
            SELECT principal.principal_id
              FROM security.entra_principal_identity AS identity
              JOIN security.principal AS principal
                ON principal.principal_id = identity.principal_id
             WHERE identity.entra_tenant_id = %s
               AND identity.entra_object_id = %s
            """,
            (ENTRA_TENANT_ID, ENTRA_OBJECT_ID),
        ).fetchone()
        assert principal is not None
        connection.execute(
            """
            INSERT INTO mcp.model_change_set (
                model_change_set_id, model_id, base_model_revision,
                base_source_context_digest, base_assertion_digest,
                base_policy_digest, created_by_principal_id, correlation_id
            ) VALUES (%s, %s, 1, %s, %s, %s, %s, %s)
            """,
            (
                change_set_id,
                model_id,
                "a" * 64,
                "b" * 64,
                "c" * 64,
                principal["principal_id"],
                UUID("50000000-0000-4000-8000-000000000072"),
            ),
        )
        connection.execute(
            """
            INSERT INTO mcp.model_stage_batch (
                stage_batch_id, model_change_set_id, model_id, dataset_name,
                expected_draft_revision, total_record_count, total_chunk_count,
                batch_sha256, created_by_principal_id, correlation_id,
                created_time, last_activity_time, expires_time
            ) VALUES (
                %s, %s, %s, 'conceptual_object', 1, 1, 1, %s, %s, %s,
                clock_timestamp() - INTERVAL '3 hours',
                clock_timestamp() - INTERVAL '2 hours',
                clock_timestamp() - INTERVAL '1 hour'
            )
            """,
            (
                stage_batch_id,
                change_set_id,
                model_id,
                "d" * 64,
                principal["principal_id"],
                UUID("60000000-0000-4000-8000-000000000072"),
            ),
        )

    with postgres_database.connect_runtime() as connection:
        touched = connection.execute(
            _TOUCH_MODEL_STAGE_BATCH_SQL,
            (stage_batch_id,),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT last_activity_time < expires_time AS activity_precedes_expiry
              FROM mcp.model_stage_batch
             WHERE stage_batch_id = %s
            """,
            (stage_batch_id,),
        ).fetchone()

    assert touched is None
    assert stored == {"activity_precedes_expiry": True}


def test_model_stage_sql_null_revision_cannot_bypass_compare_and_swap(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, _ = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_STAGE_CAS",
    )
    change_set_id = UUID("30000000-0000-4000-8000-000000000073")
    with postgres_database.connect_owner() as connection:
        principal = connection.execute(
            """
            SELECT principal.principal_id
              FROM security.entra_principal_identity AS identity
              JOIN security.principal AS principal
                ON principal.principal_id = identity.principal_id
             WHERE identity.entra_tenant_id = %s
               AND identity.entra_object_id = %s
            """,
            (ENTRA_TENANT_ID, ENTRA_OBJECT_ID),
        ).fetchone()
        assert principal is not None
        connection.execute(
            """
            INSERT INTO mcp.model_change_set (
                model_change_set_id, model_id, base_model_revision,
                base_source_context_digest, base_assertion_digest,
                base_policy_digest, created_by_principal_id, correlation_id
            ) VALUES (%s, %s, 1, %s, %s, %s, %s, %s)
            """,
            (
                change_set_id,
                model_id,
                "a" * 64,
                "b" * 64,
                "c" * 64,
                principal["principal_id"],
                UUID("40000000-0000-4000-8000-000000000073"),
            ),
        )

    with postgres_database.connect_runtime() as connection:
        staged = connection.execute(
            _STAGE_SQL,
            (
                *(Jsonb({}) for _ in WRITE_SECTION_COLUMNS),
                change_set_id,
                model_id,
                principal["principal_id"],
                None,
            ),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT model_change_set_status, draft_revision
              FROM mcp.model_change_set
             WHERE model_change_set_id = %s
            """,
            (change_set_id,),
        ).fetchone()

    assert staged is None
    assert stored == {"model_change_set_status": "active", "draft_revision": 1}


@pytest.mark.asyncio
async def test_get_model_change_set_persists_parent_and_batch_expiry_once(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_GET_EXPIRY",
    )
    _acquire_tenant_lock(postgres_database, tenant_id)
    database = postgres_database.create_runtime_adapter()
    identity_provider = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-get-expiry-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )

    await database.open()
    try:
        async with Client(server) as client:
            created = await client.call_tool(
                "create_model_change_set", {"model_id": model_id}
            )
            assert created.is_error is False
            change_set_id = created.structured_content["model_change_set_id"]
            begun = await client.call_tool(
                "begin_model_stage_batch",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 1,
                    "dataset": "conceptual_object",
                    "total_record_count": 1,
                    "total_chunk_count": 1,
                    "batch_sha256": "a" * 64,
                },
            )
            assert begun.is_error is False
            stage_batch_id = begun.structured_content["stage_batch_id"]
            with postgres_database.connect_owner() as connection:
                connection.execute(
                    """
                    UPDATE mcp.model_change_set
                       SET created_time = clock_timestamp() - INTERVAL '3 hours',
                           last_activity_time = clock_timestamp() - INTERVAL '2 hours',
                           expires_time = clock_timestamp() - INTERVAL '1 hour'
                     WHERE model_change_set_id = %s
                    """,
                    (change_set_id,),
                )

            first = await client.call_tool(
                "get_model_change_set",
                {"model_id": model_id, "model_change_set_id": change_set_id},
            )
            second = await client.call_tool(
                "get_model_change_set",
                {"model_id": model_id, "model_change_set_id": change_set_id},
            )
            assert first.is_error is False
            assert second.is_error is False
            assert first.structured_content["status"] == "expired"
            assert first.structured_content["terminal_at"] is not None
            assert second.structured_content["status"] == "expired"
    finally:
        await database.close()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT batch.stage_batch_status,
                   count(event.model_change_set_event_id) FILTER (
                       WHERE event.event_type = 'expired'
                   ) AS expired_event_count
              FROM mcp.model_stage_batch AS batch
              LEFT JOIN mcp.model_change_set_event AS event
                ON event.model_change_set_id = batch.model_change_set_id
             WHERE batch.stage_batch_id = %s
             GROUP BY batch.stage_batch_id
            """,
            (stage_batch_id,),
        ).fetchone()

    assert stored == {"stage_batch_status": "expired", "expired_event_count": 1}


@pytest.mark.asyncio
async def test_stage_model_change_set_persists_expiry_before_rejecting_mutation(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_STAGE_EXPIRY",
    )
    _acquire_tenant_lock(postgres_database, tenant_id)
    database = postgres_database.create_runtime_adapter()
    identity_provider = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-stage-expiry-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )

    await database.open()
    try:
        async with Client(server) as client:
            created = await client.call_tool(
                "create_model_change_set", {"model_id": model_id}
            )
            assert created.is_error is False
            change_set_id = created.structured_content["model_change_set_id"]
            with postgres_database.connect_owner() as connection:
                connection.execute(
                    """
                    UPDATE mcp.model_change_set
                       SET created_time = clock_timestamp() - INTERVAL '3 hours',
                           last_activity_time = clock_timestamp() - INTERVAL '2 hours',
                           expires_time = clock_timestamp() - INTERVAL '1 hour'
                     WHERE model_change_set_id = %s
                    """,
                    (change_set_id,),
                )

            staged = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 1,
                    "changes": [{"dataset": "conceptual_object", "records": []}],
                },
            )
            assert staged.is_error is True
            assert isinstance(staged.content[0], TextContent)
            assert "model_change_set_not_active" in staged.content[0].text
    finally:
        await database.close()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT change_set.model_change_set_status,
                   change_set.draft_revision,
                   count(event.model_change_set_event_id) FILTER (
                       WHERE event.event_type = 'expired'
                   ) AS expired_event_count
              FROM mcp.model_change_set AS change_set
              LEFT JOIN mcp.model_change_set_event AS event
                ON event.model_change_set_id = change_set.model_change_set_id
             WHERE change_set.model_change_set_id = %s
             GROUP BY change_set.model_change_set_id
            """,
            (change_set_id,),
        ).fetchone()

    assert stored == {
        "model_change_set_status": "expired",
        "draft_revision": 1,
        "expired_event_count": 1,
    }


@pytest.mark.asyncio
async def test_concurrent_model_change_set_create_is_one_idempotent_draft(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_CREATE_RACE",
    )
    _acquire_tenant_lock(postgres_database, tenant_id)
    database = postgres_database.create_runtime_adapter()
    identity_provider = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-create-race-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )

    await database.open()
    try:
        async with Client(server) as client:
            results = await asyncio.gather(
                client.call_tool("create_model_change_set", {"model_id": model_id}),
                client.call_tool("create_model_change_set", {"model_id": model_id}),
            )
            assert all(result.is_error is False for result in results)
            assert sorted(
                result.structured_content["created"] for result in results
            ) == [
                False,
                True,
            ]
            assert (
                len(
                    {
                        result.structured_content["model_change_set_id"]
                        for result in results
                    }
                )
                == 1
            )
    finally:
        await database.close()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT count(DISTINCT change_set.model_change_set_id) AS draft_count,
                   count(event.model_change_set_event_id) FILTER (
                       WHERE event.event_type = 'created'
                   ) AS created_event_count
              FROM mcp.model_change_set AS change_set
              LEFT JOIN mcp.model_change_set_event AS event
                ON event.model_change_set_id = change_set.model_change_set_id
             WHERE change_set.model_id = %s
               AND change_set.model_change_set_status IN ('active', 'validated')
            """,
            (model_id,),
        ).fetchone()

    assert stored == {"draft_count": 1, "created_event_count": 1}


@pytest.mark.asyncio
async def test_create_expiry_clock_is_captured_after_waiting_for_the_draft_lock(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_EXPIRY_WAIT",
    )
    _acquire_tenant_lock(postgres_database, tenant_id)
    database = postgres_database.create_runtime_adapter()
    identity_provider = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-expiry-wait-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )

    await database.open()
    try:
        async with Client(server) as client:
            initial = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert initial.is_error is False
            initial_id = initial.structured_content["model_change_set_id"]
            with postgres_database.connect_owner() as blocker:
                blocker.execute(
                    """
                    SELECT model_change_set_id
                      FROM mcp.model_change_set
                     WHERE model_change_set_id = %s
                     FOR UPDATE
                    """,
                    (initial_id,),
                ).fetchone()
                lock_time = blocker.execute(
                    "SELECT clock_timestamp() AS current_time"
                ).fetchone()
                assert lock_time is not None
                blocker.execute(
                    """
                    UPDATE mcp.model_change_set
                       SET created_time = %s - INTERVAL '1 hour',
                           last_activity_time = %s,
                           expires_time = %s + INTERVAL '100 milliseconds'
                     WHERE model_change_set_id = %s
                    """,
                    (
                        lock_time["current_time"],
                        lock_time["current_time"],
                        lock_time["current_time"],
                        initial_id,
                    ),
                )
                waiting_create = asyncio.create_task(
                    client.call_tool("create_model_change_set", {"model_id": model_id})
                )
                await asyncio.sleep(0.2)
                assert waiting_create.done() is False
                blocker.commit()
                replacement = await asyncio.wait_for(waiting_create, timeout=5)

            assert replacement.is_error is False
            assert replacement.structured_content["created"] is True
            assert replacement.structured_content["model_change_set_id"] != initial_id
    finally:
        await database.close()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
                SELECT count(DISTINCT change_set.model_change_set_id) FILTER (
                           WHERE model_change_set_status IN ('active', 'validated')
                       ) AS ongoing_count,
                       count(DISTINCT change_set.model_change_set_id) FILTER (
                               WHERE change_set.model_change_set_id = %s
                                 AND change_set.model_change_set_status = 'expired'
                   ) AS original_expired_count,
                   count(event.model_change_set_event_id) FILTER (
                       WHERE event.model_change_set_id = %s
                         AND event.event_type = 'expired'
                   ) AS expiry_event_count
              FROM mcp.model_change_set AS change_set
              LEFT JOIN mcp.model_change_set_event AS event
                ON event.model_change_set_id = change_set.model_change_set_id
             WHERE change_set.model_id = %s
            """,
            (initial_id, initial_id, model_id),
        ).fetchone()

    assert stored == {
        "ongoing_count": 1,
        "original_expired_count": 1,
        "expiry_event_count": 1,
    }


@pytest.mark.asyncio
async def test_all_model_change_set_mutation_paths_persist_due_expiry_once(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_ALL_EXPIRY",
    )
    _acquire_tenant_lock(postgres_database, tenant_id)
    database = postgres_database.create_runtime_adapter()
    identity_provider = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-all-expiry-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    conceptual_record = _replace_codes(
        complete_graph()["conceptual_object"][0],
        code_prefix="MODEL_ALL_EXPIRY",
    )
    assert isinstance(conceptual_record, dict)
    chunk_sha256 = canonical_records_sha256([conceptual_record])
    batch_sha256 = stage_batch_sha256([chunk_sha256])

    await database.open()
    try:
        async with Client(server) as client:
            for operation in ("begin", "put", "commit", "validate", "apply", "archive"):
                created = await client.call_tool(
                    "create_model_change_set",
                    {"model_id": model_id},
                )
                assert created.is_error is False
                change_set_id = created.structured_content["model_change_set_id"]
                stage_batch_id: str | None = None
                if operation in {"put", "commit"}:
                    begun = await client.call_tool(
                        "begin_model_stage_batch",
                        {
                            "model_id": model_id,
                            "model_change_set_id": change_set_id,
                            "expected_draft_revision": 1,
                            "dataset": "conceptual_object",
                            "total_record_count": 1,
                            "total_chunk_count": 1,
                            "batch_sha256": batch_sha256,
                        },
                    )
                    assert begun.is_error is False
                    stage_batch_id = begun.structured_content["stage_batch_id"]

                with postgres_database.connect_owner() as connection:
                    connection.execute(
                        """
                        UPDATE mcp.model_change_set
                           SET created_time = clock_timestamp() - INTERVAL '3 hours',
                               last_activity_time = clock_timestamp() - INTERVAL '2 hours',
                               expires_time = clock_timestamp() - INTERVAL '1 hour'
                         WHERE model_change_set_id = %s
                        """,
                        (change_set_id,),
                    )

                if operation == "begin":
                    result = await client.call_tool(
                        "begin_model_stage_batch",
                        {
                            "model_id": model_id,
                            "model_change_set_id": change_set_id,
                            "expected_draft_revision": 1,
                            "dataset": "conceptual_object",
                            "total_record_count": 1,
                            "total_chunk_count": 1,
                            "batch_sha256": batch_sha256,
                        },
                    )
                elif operation == "put":
                    assert stage_batch_id is not None
                    result = await client.call_tool(
                        "put_model_stage_chunk",
                        {
                            "model_id": model_id,
                            "model_change_set_id": change_set_id,
                            "stage_batch_id": stage_batch_id,
                            "dataset": "conceptual_object",
                            "chunk_index": 1,
                            "records": [conceptual_record],
                            "chunk_sha256": chunk_sha256,
                        },
                    )
                elif operation == "commit":
                    assert stage_batch_id is not None
                    result = await client.call_tool(
                        "commit_model_stage_batch",
                        {
                            "model_id": model_id,
                            "model_change_set_id": change_set_id,
                            "stage_batch_id": stage_batch_id,
                            "expected_draft_revision": 1,
                        },
                    )
                else:
                    result = await client.call_tool(
                        f"{operation}_model_change_set",
                        {
                            "model_id": model_id,
                            "model_change_set_id": change_set_id,
                            "expected_draft_revision": 1,
                        },
                    )

                assert result.is_error is True, operation
                assert isinstance(result.content[0], TextContent)
                assert "model_change_set_not_active" in result.content[0].text
                with postgres_database.connect_owner() as connection:
                    stored = connection.execute(
                        """
                        SELECT change_set.model_change_set_status,
                               count(event.model_change_set_event_id) FILTER (
                                   WHERE event.event_type = 'expired'
                               ) AS expired_event_count,
                               count(batch.stage_batch_id) FILTER (
                                   WHERE batch.stage_batch_status = 'active'
                               ) AS active_batch_count
                          FROM mcp.model_change_set AS change_set
                          LEFT JOIN mcp.model_change_set_event AS event
                            ON event.model_change_set_id =
                               change_set.model_change_set_id
                          LEFT JOIN mcp.model_stage_batch AS batch
                            ON batch.model_change_set_id =
                               change_set.model_change_set_id
                         WHERE change_set.model_change_set_id = %s
                         GROUP BY change_set.model_change_set_id
                        """,
                        (change_set_id,),
                    ).fetchone()
                assert stored == {
                    "model_change_set_status": "expired",
                    "expired_event_count": 1,
                    "active_batch_count": 0,
                }, operation
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_put_and_commit_persist_due_model_stage_batch_expiry(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_BATCH_EXPIRY",
    )
    _acquire_tenant_lock(postgres_database, tenant_id)
    database = postgres_database.create_runtime_adapter()
    identity_provider = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-batch-expiry-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )
    conceptual_record = _replace_codes(
        complete_graph()["conceptual_object"][0],
        code_prefix="MODEL_BATCH_EXPIRY",
    )
    assert isinstance(conceptual_record, dict)
    chunk_sha256 = canonical_records_sha256([conceptual_record])
    batch_sha256 = stage_batch_sha256([chunk_sha256])

    await database.open()
    try:
        async with Client(server) as client:
            created = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert created.is_error is False
            change_set_id = created.structured_content["model_change_set_id"]
            expired_batch_ids: list[str] = []
            for operation in ("put", "commit"):
                begun = await client.call_tool(
                    "begin_model_stage_batch",
                    {
                        "model_id": model_id,
                        "model_change_set_id": change_set_id,
                        "expected_draft_revision": 1,
                        "dataset": "conceptual_object",
                        "total_record_count": 1,
                        "total_chunk_count": 1,
                        "batch_sha256": batch_sha256,
                    },
                )
                assert begun.is_error is False
                stage_batch_id = begun.structured_content["stage_batch_id"]
                expired_batch_ids.append(stage_batch_id)
                with postgres_database.connect_owner() as connection:
                    connection.execute(
                        """
                        UPDATE mcp.model_stage_batch
                           SET created_time = clock_timestamp() - INTERVAL '3 hours',
                               last_activity_time = clock_timestamp() - INTERVAL '2 hours',
                               expires_time = clock_timestamp() - INTERVAL '1 hour'
                         WHERE stage_batch_id = %s
                        """,
                        (stage_batch_id,),
                    )

                if operation == "put":
                    result = await client.call_tool(
                        "put_model_stage_chunk",
                        {
                            "model_id": model_id,
                            "model_change_set_id": change_set_id,
                            "stage_batch_id": stage_batch_id,
                            "dataset": "conceptual_object",
                            "chunk_index": 1,
                            "records": [conceptual_record],
                            "chunk_sha256": chunk_sha256,
                        },
                    )
                else:
                    result = await client.call_tool(
                        "commit_model_stage_batch",
                        {
                            "model_id": model_id,
                            "model_change_set_id": change_set_id,
                            "stage_batch_id": stage_batch_id,
                            "expected_draft_revision": 1,
                        },
                    )
                assert result.is_error is True
                assert isinstance(result.content[0], TextContent)
                assert "stage_batch_not_active" in result.content[0].text
    finally:
        await database.close()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT count(*) FILTER (
                       WHERE stage_batch_status = 'expired'
                   ) AS expired_batch_count
              FROM mcp.model_stage_batch
             WHERE stage_batch_id = ANY(%s::UUID[])
            """,
            (expired_batch_ids,),
        ).fetchone()

    assert stored == {"expired_batch_count": 2}


@pytest.mark.asyncio
async def test_model_stage_batch_runs_through_validate_and_apply(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_BATCH",
    )
    staged = _replace_codes(complete_graph(), code_prefix="MODEL_BATCH")
    conceptual_objects = staged.pop("conceptual_object")
    assert len(conceptual_objects) == 2
    chunks = [[conceptual_objects[0]], [conceptual_objects[1]]]
    chunk_sha256s = [canonical_records_sha256(chunk) for chunk in chunks]
    batch_sha256 = stage_batch_sha256(chunk_sha256s)
    _acquire_tenant_lock(postgres_database, tenant_id)

    database = postgres_database.create_runtime_adapter()
    identity_provider = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-stage-batch-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )

    await database.open()
    try:
        async with Client(server) as client:
            created = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert created.is_error is False
            change_set_id = created.structured_content["model_change_set_id"]
            normally_staged = await client.call_tool(
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
            assert normally_staged.is_error is False
            assert normally_staged.structured_content["draft_revision"] == 2

            begun = await client.call_tool(
                "begin_model_stage_batch",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 2,
                    "dataset": "conceptual_object",
                    "total_record_count": 2,
                    "total_chunk_count": 2,
                    "batch_sha256": batch_sha256,
                },
            )
            assert begun.is_error is False
            stage_batch_id = begun.structured_content["stage_batch_id"]
            resumed = await client.call_tool(
                "begin_model_stage_batch",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 2,
                    "dataset": "conceptual_object",
                    "total_record_count": 2,
                    "total_chunk_count": 2,
                    "batch_sha256": batch_sha256,
                },
            )
            assert resumed.is_error is False
            assert resumed.structured_content["created"] is False
            assert resumed.structured_content["stage_batch_id"] == stage_batch_id

            for index, (chunk, chunk_sha256) in enumerate(
                zip(chunks, chunk_sha256s, strict=True),
                start=1,
            ):
                put = await client.call_tool(
                    "put_model_stage_chunk",
                    {
                        "model_id": model_id,
                        "model_change_set_id": change_set_id,
                        "stage_batch_id": stage_batch_id,
                        "dataset": "conceptual_object",
                        "chunk_index": index,
                        "records": chunk,
                        "chunk_sha256": chunk_sha256,
                    },
                )
                assert put.is_error is False
                assert put.structured_content["received_chunk_count"] == index
                if index == 1:
                    incomplete = await client.call_tool(
                        "commit_model_stage_batch",
                        {
                            "model_id": model_id,
                            "model_change_set_id": change_set_id,
                            "stage_batch_id": stage_batch_id,
                            "expected_draft_revision": 2,
                        },
                    )
                    assert incomplete.is_error is True
                    assert isinstance(incomplete.content[0], TextContent)
                    assert "stage_batch_incomplete" in incomplete.content[0].text

            committed = await client.call_tool(
                "commit_model_stage_batch",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "stage_batch_id": stage_batch_id,
                    "expected_draft_revision": 2,
                },
            )
            assert committed.is_error is False
            assert committed.structured_content["draft_revision"] == 3
            assert committed.structured_content["record_count"] == 2
            replayed = await client.call_tool(
                "commit_model_stage_batch",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "stage_batch_id": stage_batch_id,
                    "expected_draft_revision": 2,
                },
            )
            assert replayed.is_error is False
            assert replayed.structured_content["replayed"] is True
            assert replayed.structured_content["draft_revision"] == 3

            pending = await client.call_tool(
                "get_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "dataset": "conceptual_object",
                },
            )
            assert pending.is_error is False
            assert pending.structured_content["records"] == conceptual_objects
            validated = await client.call_tool(
                "validate_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 3,
                },
            )
            assert validated.is_error is False
            assert validated.structured_content["valid"] is True
            applied = await client.call_tool(
                "apply_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 3,
                },
            )
            assert applied.is_error is False
            assert applied.structured_content["applied"] is True
            terminal_replay = await client.call_tool(
                "commit_model_stage_batch",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "stage_batch_id": stage_batch_id,
                    "expected_draft_revision": 2,
                },
            )
            assert terminal_replay.is_error is True
            assert isinstance(terminal_replay.content[0], TextContent)
            assert "model_change_set_not_active" in terminal_replay.content[0].text
    finally:
        await database.close()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT stage_batch_status, committed_revision
              FROM mcp.model_stage_batch
             WHERE stage_batch_id = %s
            """,
            (stage_batch_id,),
        ).fetchone()
        section_puts = connection.execute(
            """
            SELECT count(*) AS count
              FROM mcp.model_change_set_event
             WHERE model_change_set_id = %s
               AND event_type = 'section_put'
            """,
            (change_set_id,),
        ).fetchone()

    assert stored == {"stage_batch_status": "committed", "committed_revision": 3}
    assert section_puts == {"count": 2}


@pytest.mark.asyncio
async def test_model_stage_batch_reassembles_generated_code_json_fragments(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_CODE_FRAGMENTS",
    )
    _acquire_tenant_lock(postgres_database, tenant_id)
    content = "-- " + ("x" * 1_100_000) + " café\nSELECT 1 AS result;"
    record: dict[str, object] = {
        "tenant_code": "MODEL_CODE_FRAGMENTS",
        "system_code": "MODEL_CODE_FRAGMENTS_SYSTEM",
        "connection_code": "MODEL_CODE_FRAGMENTS_CONNECTION",
        "object_schema": "silver",
        "object_name": "fragmented_code",
        "modeled_entity_type": "logical_entity",
        "artifact_type": "sql_file",
        "generated_code_content": content,
        "mapping_context_digest": "1" * 64,
        "source_context_digest": "2" * 64,
        "generated_code_digest": hashlib.sha256(content.encode()).hexdigest(),
        "generated_code_status": "active",
        "generated_code_is_locked": False,
    }
    payload = json.dumps(
        [record],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    unicode_offset = payload.index("é".encode())
    fragments = [
        payload[:MAX_MODEL_STAGE_CHUNK_BYTES],
        payload[MAX_MODEL_STAGE_CHUNK_BYTES : unicode_offset + 1],
        payload[unicode_offset + 1 :],
    ]
    assert len(payload) > MAX_MODEL_STAGE_CHUNK_BYTES
    assert all(
        0 < len(fragment) <= MAX_MODEL_STAGE_CHUNK_BYTES for fragment in fragments
    )
    chunk_hashes = [hashlib.sha256(fragment).hexdigest() for fragment in fragments]

    database = postgres_database.create_runtime_adapter()
    identity_provider = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-code-fragment-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )

    await database.open()
    try:
        async with Client(server) as client:
            created = await client.call_tool(
                "create_model_change_set", {"model_id": model_id}
            )
            assert created.is_error is False
            change_set_id = created.structured_content["model_change_set_id"]
            begun = await client.call_tool(
                "begin_model_stage_batch",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 1,
                    "dataset": "generated_code",
                    "payload_mode": "json_fragments",
                    "total_record_count": 1,
                    "total_chunk_count": len(fragments),
                    "total_payload_bytes": len(payload),
                    "batch_sha256": stage_batch_sha256(chunk_hashes),
                },
            )
            assert begun.is_error is False
            assert begun.structured_content["payload_mode"] == "json_fragments"
            assert begun.structured_content["total_payload_bytes"] == len(payload)
            stage_batch_id = begun.structured_content["stage_batch_id"]

            for index, (fragment, chunk_hash) in enumerate(
                zip(fragments, chunk_hashes, strict=True),
                start=1,
            ):
                put = await client.call_tool(
                    "put_model_stage_chunk",
                    {
                        "model_id": model_id,
                        "model_change_set_id": change_set_id,
                        "stage_batch_id": stage_batch_id,
                        "dataset": "generated_code",
                        "payload_mode": "json_fragments",
                        "chunk_index": index,
                        "payload_fragment_base64": base64.b64encode(fragment).decode(),
                        "chunk_sha256": chunk_hash,
                    },
                )
                assert put.is_error is False
                assert put.structured_content["record_count"] == 0
                assert put.structured_content["payload_byte_count"] == len(fragment)

            committed = await client.call_tool(
                "commit_model_stage_batch",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "stage_batch_id": stage_batch_id,
                    "expected_draft_revision": 1,
                },
            )
            assert committed.is_error is False
            assert committed.structured_content["draft_revision"] == 2
            pending = await client.call_tool(
                "get_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "dataset": "generated_code",
                },
            )
            assert pending.is_error is False
            assert pending.structured_content["records"] == [record]
    finally:
        await database.close()

    with postgres_database.connect_owner() as connection:
        audited_chunks = connection.execute(
            """
            SELECT input_metadata
              FROM mcp.tool_call_log
             WHERE tool_name = 'put_model_stage_chunk'
               AND input_metadata ->> 'stage_batch_id' = %s
             ORDER BY (input_metadata ->> 'chunk_index')::INTEGER
            """,
            (stage_batch_id,),
        ).fetchall()

    assert len(audited_chunks) == len(fragments)
    for row, fragment in zip(audited_chunks, fragments, strict=True):
        metadata = row["input_metadata"]
        assert "payload_fragment_base64" not in metadata
        assert "payload_fragment" not in metadata
        assert metadata["payload_fragment_base64_characters"] == len(
            base64.b64encode(fragment)
        )


@pytest.mark.asyncio
async def test_model_change_set_policy_digest_includes_canonical_json_templates(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(
        postgres_database,
        code_prefix="MODEL_POLICY",
    )
    _acquire_tenant_lock(postgres_database, tenant_id)
    database = postgres_database.create_runtime_adapter()
    identity_provider = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-policy-digest-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
    )

    await database.open()
    try:
        async with Client(server) as client:
            digests: list[str] = []
            updates = (
                (
                    "silver_model_audit_columns_template",
                    {"silver_audit": {"b": 2, "a": 1}},
                ),
                (
                    "gold_model_technical_columns_template",
                    {"gold_technical": ["surrogate_key"]},
                ),
                (
                    "gold_model_audit_columns_template",
                    {"gold_audit": {"b": 2, "a": 1}},
                ),
            )
            for update_index in range(len(updates) + 1):
                created = await client.call_tool(
                    "create_model_change_set",
                    {"model_id": model_id},
                )
                assert created.is_error is False
                change_set_id = created.structured_content["model_change_set_id"]
                with postgres_database.connect_owner() as connection:
                    row = connection.execute(
                        """
                        SELECT base_policy_digest
                          FROM mcp.model_change_set
                         WHERE model_change_set_id = %s
                        """,
                        (change_set_id,),
                    ).fetchone()
                assert row is not None
                digests.append(row["base_policy_digest"])
                archived = await client.call_tool(
                    "archive_model_change_set",
                    {
                        "model_id": model_id,
                        "model_change_set_id": change_set_id,
                        "expected_draft_revision": 1,
                    },
                )
                assert archived.is_error is False
                if update_index < len(updates):
                    column_name, template = updates[update_index]
                    with postgres_database.connect_owner() as connection:
                        connection.execute(
                            sql.SQL(
                                """
                                UPDATE model.model
                                   SET {} = %s::JSONB
                                 WHERE model_id = %s
                                """
                            ).format(sql.Identifier(column_name)),
                            (json.dumps(template), model_id),
                        )

            assert len(set(digests)) == 4

            with postgres_database.connect_owner() as connection:
                connection.execute(
                    """
                    UPDATE model.model
                       SET gold_model_audit_columns_template = %s::JSONB
                     WHERE model_id = %s
                    """,
                    (json.dumps({"gold_audit": {"a": 1, "b": 2}}), model_id),
                )
            reordered = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert reordered.is_error is False
            with postgres_database.connect_owner() as connection:
                reordered_row = connection.execute(
                    """
                    SELECT base_policy_digest
                      FROM mcp.model_change_set
                     WHERE model_change_set_id = %s
                    """,
                    (reordered.structured_content["model_change_set_id"],),
                ).fetchone()
            assert reordered_row is not None
            assert reordered_row["base_policy_digest"] == digests[-1]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_all_model_datasets_materialize_and_round_trip_as_one_snapshot(
    postgres_database: DisposablePostgres,
) -> None:
    model_id, tenant_id = _seed_model_foundation(postgres_database)
    staged = _replace_codes(complete_graph())
    scope_records = _replace_codes(model_scope_records())
    for field in ANALYSIS_VALIDATION_FIELDS:
        staged["analysis_result"][0].pop(field)
    with postgres_database.connect_owner() as connection:
        mapping_ids = connection.execute(
            """
            SELECT system.system_id AS source_system_id,
                   max(object.object_id) FILTER (
                       WHERE lower(btrim(object.object_name)) = 'orders'
                   ) AS source_object_id,
                   max(attribute.attribute_id) FILTER (
                       WHERE lower(btrim(object.object_name)) = 'orders'
                         AND lower(btrim(attribute.attribute_name)) = 'customer_id'
                   ) AS source_attribute_id,
                   max(object.object_id) FILTER (
                       WHERE lower(btrim(object.object_name)) = 'silver_orders'
                   ) AS target_object_id,
                   max(attribute.attribute_id) FILTER (
                       WHERE lower(btrim(object.object_name)) = 'silver_orders'
                         AND lower(btrim(attribute.attribute_name)) = 'customer_id'
                   ) AS target_attribute_id
              FROM core.system AS system
              JOIN core.connection AS connection
                ON connection.system_id = system.system_id
               AND connection.tenant_id = %s
              JOIN core.object AS object
                ON object.connection_id = connection.connection_id
              JOIN core.attribute AS attribute
                ON attribute.object_id = object.object_id
             WHERE lower(btrim(system.system_code)) = 'model_tool_erp'
             GROUP BY system.system_id
            """,
            (tenant_id,),
        ).fetchone()
    assert mapping_ids is not None
    assert all(isinstance(value, int) for value in mapping_ids.values())
    source_system_id = cast(int, mapping_ids["source_system_id"])
    source_object_id = cast(int, mapping_ids["source_object_id"])
    source_attribute_id = cast(int, mapping_ids["source_attribute_id"])
    target_object_id = cast(int, mapping_ids["target_object_id"])
    target_attribute_id = cast(int, mapping_ids["target_attribute_id"])
    generation_instructions = "Generate deterministic Databricks SQL."
    staged["mapping_object"][0].update(
        {
            "artifact_type": "sql_file",
            "artifact_generation_instructions": generation_instructions,
            "mapping_profile_key": "mapping.standard",
            "mapping_profile_version": "1.0.0",
            "mapping_package_document": {
                "schema_version": "1.0",
                "package_ref": "silver_orders_erp",
                "route": "logical_to_silver",
                "target_object_id": target_object_id,
                "source_system_id": source_system_id,
                "artifact_type": "sql_file",
                "artifact_generation_instructions": generation_instructions,
                "pydantic_profile": {
                    "key": "mapping.standard",
                    "version": "1.0.0",
                    "schema_digest": (
                        "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
                    ),
                },
                "executable_sources": [
                    {
                        "object_id": source_object_id,
                        "alias": "orders_source",
                        "role": "Orders source",
                        "batch_rule": None,
                    }
                ],
                "non_executable_provenance": [],
                "runtime_parameters": [],
                "source_system_dependencies": [],
                "target_dependencies": [],
                "steps": [
                    {
                        "name": "load_orders",
                        "depends_on": [],
                        "inputs": ["orders_source"],
                        "output": "order_rows",
                        "logic": "Load governed Order rows.",
                    }
                ],
                "grain_and_deduplication": "One row per Order.",
                "load": {
                    "write_mode": "merge",
                    "merge_keys": [target_attribute_id],
                    "partition_basis": None,
                    "concurrent_system_write_mode": "idempotent_merge",
                    "concurrent_write_basis": "Order customer key.",
                },
            },
            "object_mapping_transformation_document": {
                "schema_version": "1.0",
                "transformation_kind": "direct",
                "source_aliases": ["orders_source"],
                "joins": [],
                "unions": [],
                "filters": [],
                "aggregations": [],
                "entity_contribution_logic": "Orders source contributes Order rows.",
                "rationale": "The governed ERP source directly represents Orders.",
            },
        }
    )
    staged["mapping_attribute"][0]["attribute_mapping_transformation_document"] = {
        "schema_version": "1.0",
        "transformation_kind": "direct",
        "source_columns": [
            {
                "source_alias": "orders_source",
                "source_attribute_id": source_attribute_id,
            }
        ],
        "step_output": None,
        "expression": None,
        "logic": "Copy the governed Order customer key.",
    }
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
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    register_get_model_scope_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=b"development-only-key-32-bytes-long",
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
            assert returned_model["model_scope_object_count"] == 4
            initial_scope = await client.call_tool(
                "get_model_scope",
                {"model_id": model_id},
            )
            assert initial_scope.is_error is False
            assert initial_scope.structured_content["object_count"] == 4
            initial_scope_by_name = {
                item["object_name"]: item
                for item in initial_scope.structured_content["objects"]
            }
            assert initial_scope_by_name["orders"]["is_bronze_source_eligible"] is True
            assert (
                initial_scope_by_name["silver_orders"][
                    "is_logical_mapping_target_eligible"
                ]
                is True
            )
            assert (
                initial_scope_by_name["silver_orders"]["is_dimensional_source_eligible"]
                is False
            )
            assert (
                initial_scope_by_name["gold_sales"][
                    "is_dimensional_mapping_target_eligible"
                ]
                is True
            )
            created = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert created.is_error is False
            change_set_id = created.structured_content["model_change_set_id"]
            rejected_scope_stage = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 1,
                    "changes": [{"dataset": "model_scope", "records": scope_records}],
                },
            )
            assert rejected_scope_stage.is_error is True
            with postgres_database.connect_owner() as connection:
                connection.execute(
                    """
                    UPDATE mcp.model_change_set
                       SET model_scope_document = %s::JSONB
                     WHERE model_change_set_id = %s
                    """,
                    (
                        json.dumps({"model_scope": scope_records}),
                        change_set_id,
                    ),
                )
            rejected_scope_validation = await client.call_tool(
                "validate_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 1,
                },
            )
            assert rejected_scope_validation.is_error is True
            assert isinstance(rejected_scope_validation.content[0], TextContent)
            assert (
                "not writable through MCP" in rejected_scope_validation.content[0].text
            )
            with postgres_database.connect_owner() as connection:
                connection.execute(
                    """
                    UPDATE mcp.model_change_set
                       SET model_change_set_status = 'validated',
                           candidate_digest = repeat('a', 64)
                     WHERE model_change_set_id = %s
                    """,
                    (change_set_id,),
                )
            rejected_scope_apply = await client.call_tool(
                "apply_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 1,
                },
            )
            assert rejected_scope_apply.is_error is True
            assert isinstance(rejected_scope_apply.content[0], TextContent)
            assert "not writable through MCP" in rejected_scope_apply.content[0].text
            with postgres_database.connect_owner() as connection:
                connection.execute(
                    """
                    UPDATE mcp.model_change_set
                       SET model_change_set_status = 'active',
                           candidate_digest = NULL,
                           validation_outcome = NULL,
                           validated_time = NULL,
                           model_scope_document = '{}'::JSONB
                     WHERE model_change_set_id = %s
                    """,
                    (change_set_id,),
                )
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
            assert len(validated.structured_content["action_review"]) == 17
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

            with postgres_database.connect_owner() as connection:
                context_row = connection.execute(
                    """
                    SELECT tenant.tenant_code,
                           system.system_code,
                           connection.connection_code,
                           object.object_schema,
                           object.object_name,
                           context.modeled_entity_type,
                           btrim(context.mapping_context_digest)::TEXT
                               AS mapping_context_digest,
                           btrim(context.source_context_digest)::TEXT
                               AS source_context_digest,
                           ARRAY(
                               SELECT source_system ->> 'system_code'
                                 FROM jsonb_array_elements(
                                          context.source_context -> 'source_systems'
                                      ) AS source_system
                           ) AS source_system_codes
                      FROM workflow.list_code_generation_target_context(
                               %s,
                               'logical_entity'
                           ) AS context
                      JOIN core.object AS object
                        ON object.object_id = context.object_id
                      JOIN core.connection AS connection
                        ON connection.connection_id = object.connection_id
                      JOIN core.tenant AS tenant
                        ON tenant.tenant_id = connection.tenant_id
                      JOIN core.system AS system
                        ON system.system_id = connection.system_id
                     WHERE lower(btrim(object.object_name)) = 'silver_orders'
                    """,
                    (model_id,),
                ).fetchone()
            assert context_row is not None
            source_system_codes = frozenset(
                cast(list[str], context_row["source_system_codes"])
            )
            assert len(source_system_codes) == 1
            code_context = CodeGenerationTargetContext(
                object_key=tuple(
                    normalize_model_key_value(cast(str, context_row[field]))
                    for field in (
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                    )
                ),
                modeled_entity_type=cast(str, context_row["modeled_entity_type"]),
                source_system_codes=source_system_codes,
                mapping_context_digest=cast(str, context_row["mapping_context_digest"]),
                source_context_digest=cast(str, context_row["source_context_digest"]),
            )
            generated_code_content = (
                "CREATE OR REPLACE TEMP VIEW prepared_orders AS SELECT 1 AS order_id;\n"
                "SELECT * FROM prepared_orders;"
            )
            generated_code_record: dict[str, object] = {
                "tenant_code": code_context.object_key[0],
                "system_code": code_context.object_key[1],
                "connection_code": code_context.object_key[2],
                "object_schema": code_context.object_key[3],
                "object_name": code_context.object_key[4],
                "modeled_entity_type": code_context.modeled_entity_type,
                "artifact_type": "sql_file",
                "generated_code_content": generated_code_content,
                "mapping_context_digest": code_context.mapping_context_digest,
                "source_context_digest": code_context.source_context_digest,
                "generated_code_digest": hashlib.sha256(
                    generated_code_content.encode("utf-8")
                ).hexdigest(),
                "generated_code_status": "active",
                "generated_code_is_locked": False,
            }
            code_change_set = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert code_change_set.is_error is False
            code_change_set_id = code_change_set.structured_content[
                "model_change_set_id"
            ]
            code_stage = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": code_change_set_id,
                    "expected_draft_revision": 1,
                    "changes": [
                        {
                            "dataset": "generated_code",
                            "records": [generated_code_record],
                        }
                    ],
                },
            )
            assert code_stage.is_error is False
            code_validation = await client.call_tool(
                "validate_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": code_change_set_id,
                    "expected_draft_revision": 2,
                },
            )
            assert code_validation.is_error is False
            assert code_validation.structured_content["valid"] is True
            assert len(code_validation.structured_content["action_review"]) == 1
            code_apply = await client.call_tool(
                "apply_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": code_change_set_id,
                    "expected_draft_revision": 2,
                },
            )
            assert code_apply.is_error is False
            action_count += code_apply.structured_content["action_count"]

            qa_system_code = next(iter(code_context.source_system_codes))
            qa_mapping_digest = qa_mapping_context_digest(
                (code_context,),
                qa_system_code,
            )
            qa_code_digest = qa_code_context_digest(
                (code_context,),
                (GeneratedCodeRecord.model_validate(generated_code_record),),
                qa_system_code,
            )
            assert qa_mapping_digest is not None
            assert qa_code_digest is not None
            validation_group_record: dict[str, object] = {
                "tenant_code": code_context.object_key[0],
                "system_code": qa_system_code,
                "validation_group_name": "Order QA",
                "validation_group_description": "Order pipeline checks.",
                "mapping_context_digest": qa_mapping_digest,
                "code_context_digest": qa_code_digest,
                "is_active": True,
            }
            validation_check_record: dict[str, object] = {
                "tenant_code": code_context.object_key[0],
                "system_code": qa_system_code,
                "validation_group_name": "Order QA",
                "validation_check_name": "Query executes",
                "validation_check_description": "The governed QA query completes.",
                "validation_category_code": "technical.execution",
                "validation_severity": "blocking",
                "validation_query_sql": "CREATE TEMP VIEW qa_probe AS SELECT 1",
                "validation_comparison_query_sql": None,
                "validation_result_data_type": None,
                "validation_comparison_operator": "executes_successfully",
                "validation_comparison_value_type": "none",
                "validation_comparison_value": None,
                "is_active": True,
            }
            qa_change_set = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert qa_change_set.is_error is False
            qa_change_set_id = qa_change_set.structured_content["model_change_set_id"]
            qa_stage = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": qa_change_set_id,
                    "expected_draft_revision": 1,
                    "changes": [
                        {
                            "dataset": "validation_group",
                            "records": [validation_group_record],
                        },
                        {
                            "dataset": "validation_check",
                            "records": [validation_check_record],
                        },
                    ],
                },
            )
            assert qa_stage.is_error is False
            qa_validation = await client.call_tool(
                "validate_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": qa_change_set_id,
                    "expected_draft_revision": 2,
                },
            )
            assert qa_validation.is_error is False
            assert qa_validation.structured_content["valid"] is True
            assert len(qa_validation.structured_content["action_review"]) == 2
            qa_apply = await client.call_tool(
                "apply_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": qa_change_set_id,
                    "expected_draft_revision": 2,
                },
            )
            assert qa_apply.is_error is False
            action_count += qa_apply.structured_content["action_count"]

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
            assert descriptor["model_revision"] == 4
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
            assert dbml_descriptor["model_revision"] == 4
            assert dbml_descriptor["model_type"] == "full"
            assert dbml_descriptor["include_submodels"] is True
            assert dbml_descriptor["dbml_file_count"] == 5
            _assert_dbml_archive(snapshot_store.archive_content["dbml"])
            await _assert_focused_reads(client, model_id)
            active_scope = await client.call_tool(
                "get_model_scope",
                {"model_id": model_id},
            )
            assert active_scope.is_error is False
            assert active_scope.structured_content["object_count"] == 4
            active_scope_by_name = {
                item["object_name"]: item
                for item in active_scope.structured_content["objects"]
            }
            assert (
                active_scope_by_name["silver_orders"]["is_dimensional_source_eligible"]
                is True
            )
            renamed_relationship = deepcopy(staged["dimensional_relationship"][0])
            renamed_relationship["dimensional_relationship_name"] = "sale customer role"
            rename_change_set = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert rename_change_set.is_error is False
            rename_change_set_id = rename_change_set.structured_content[
                "model_change_set_id"
            ]
            rename_stage = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": rename_change_set_id,
                    "expected_draft_revision": 1,
                    "changes": [
                        {
                            "dataset": "dimensional_relationship",
                            "records": [renamed_relationship],
                        }
                    ],
                },
            )
            assert rename_stage.is_error is False
            rename_validation = await client.call_tool(
                "validate_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": rename_change_set_id,
                    "expected_draft_revision": 2,
                },
            )
            assert rename_validation.is_error is False
            assert rename_validation.structured_content["valid"] is True
            rename_apply = await client.call_tool(
                "apply_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": rename_change_set_id,
                    "expected_draft_revision": 2,
                },
            )
            assert rename_apply.is_error is False
            assert rename_apply.structured_content["action_count"] == 1
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
            invalid_eligibility = await client.call_tool(
                "create_model_change_set",
                {"model_id": model_id},
            )
            assert invalid_eligibility.is_error is False
            invalid_eligibility_id = invalid_eligibility.structured_content[
                "model_change_set_id"
            ]
            non_bronze_profile = deepcopy(staged["profiling_profile"][0])
            non_bronze_profile["object_name"] = "silver_orders"
            invalid_stage = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": invalid_eligibility_id,
                    "expected_draft_revision": 1,
                    "changes": [
                        {
                            "dataset": "profiling_profile",
                            "records": [non_bronze_profile],
                        }
                    ],
                },
            )
            assert invalid_stage.is_error is False
            invalid_validation = await client.call_tool(
                "validate_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": invalid_eligibility_id,
                    "expected_draft_revision": 2,
                },
            )
            assert invalid_validation.is_error is False
            assert invalid_validation.structured_content["valid"] is False
            assert invalid_validation.structured_content["phase"] == "model_scope"
    finally:
        await database.close()

    with postgres_database.connect_owner() as connection:
        inference_only_row = connection.execute(
            """
            SELECT validation_source_context_digest,
                   validation_policy_version,
                   validation_policy_digest,
                   validation_result,
                   validation_source_non_null_count,
                   validation_source_distinct_count,
                   validation_target_non_null_count,
                   validation_target_distinct_count,
                   validation_source_missing_target_count,
                   validation_unused_target_count,
                   validation_duplicate_target_key_count
              FROM workflow.analysis_result
             WHERE model_id = %s
            """,
            (model_id,),
        ).fetchone()
        modeled_layer_provenance = connection.execute(
            """
            SELECT sum(non_null_count)::BIGINT AS non_null_count
              FROM (
                    SELECT count(*) AS non_null_count
                      FROM workflow.logical_submodel
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.logical_entity
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.logical_entity_submodel
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.logical_entity_source_mapping
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.logical_attribute
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.logical_attribute_source_mapping
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.logical_relationship
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.dimensional_submodel
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.dimensional_entity
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.dimensional_entity_submodel
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.dimensional_entity_source_mapping
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.dimensional_attribute
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.dimensional_attribute_source_mapping
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
                    UNION ALL
                    SELECT count(*) FROM workflow.dimensional_relationship
                     WHERE model_id = %s AND workflow_run_id IS NOT NULL
              ) AS counts
            """,
            (model_id,) * 14,
        ).fetchone()
        dimensional_relationship = connection.execute(
            """
            SELECT count(*) AS relationship_count,
                   min(dimensional_relationship_name) AS relationship_name,
                   bool_and(NOT dimensional_relationship_is_optional)
                       AS relationship_is_required
              FROM workflow.dimensional_relationship
             WHERE model_id = %s
            """,
            (model_id,),
        ).fetchone()

    assert inference_only_row is not None
    assert set(inference_only_row.values()) == {None}
    assert modeled_layer_provenance == {"non_null_count": 0}
    assert dimensional_relationship == {
        "relationship_count": 1,
        "relationship_name": "sale customer role",
        "relationship_is_required": True,
    }
    assert action_count == 36
    assert snapshot_counts == {
        "model_details": 1,
        "model_scope": 4,
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
        "generated_code": 1,
        "qa_authoring_context": 1,
        "validation_group": 1,
        "validation_check": 1,
    }
    for forbidden in (
        "agent_run_id",
        "created_by",
        "created_time",
        "updated_by",
        "updated_time",
        "analysis_result_id",
        "generated_code_id",
        "validation_group_id",
        "validation_check_id",
    ):
        assert forbidden not in serialized
    assert (
        f'"mapping_context_digest":"{code_context.mapping_context_digest}"'
        in serialized
    )
    assert (
        f'"source_context_digest":"{code_context.source_context_digest}"' in serialized
    )
    assert '"zone_code":"bronze"' in serialized
    assert '"is_bronze_source_eligible":true' in serialized
    assert '"is_dimensional_source_eligible":true' in serialized
    assert '"current_code_target_count":1' in serialized
    assert '"current_code_references":[' in serialized
    assert '"dimensional_relationship_is_optional":false' in serialized


def _seed_model_foundation(
    postgres_database: DisposablePostgres,
    *,
    code_prefix: str = "MODEL_TOOL",
) -> tuple[int, int]:
    with postgres_database.connect_owner() as connection:
        system_type_id = _required_id(
            connection.execute(
                """
            INSERT INTO reference.system_type (system_type_code, system_type_name)
            VALUES (%s, %s)
            RETURNING system_type_id
            """,
                (f"{code_prefix}_DATABASE", f"{code_prefix} Database"),
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
            VALUES (%s, %s)
            RETURNING connection_type_id
            """,
                (f"{code_prefix}_POSTGRES", f"{code_prefix} Postgres"),
            ).fetchone(),
            "connection_type_id",
        )
        object_type_id = _required_id(
            connection.execute(
                """
            INSERT INTO reference.object_type (object_type_code, object_type_name)
            VALUES (%s, %s)
            RETURNING object_type_id
            """,
                (f"{code_prefix}_TABLE", f"{code_prefix} Table"),
            ).fetchone(),
            "object_type_id",
        )
        zone_ids: dict[str, int] = {}
        for zone_code in ("bronze", "silver", "gold"):
            zone = connection.execute(
                """
                SELECT zone_id
                  FROM reference.zone
                 WHERE lower(btrim(zone_code)) = %s
                """,
                (zone_code,),
            ).fetchone()
            if zone is None:
                zone = connection.execute(
                    """
                INSERT INTO reference.zone (zone_code, zone_name)
                VALUES (%s, %s)
                RETURNING zone_id
                """,
                    (zone_code, zone_code.title()),
                ).fetchone()
            zone_ids[zone_code] = _required_id(zone, "zone_id")
        project_id = _required_id(
            connection.execute(
                """
            INSERT INTO core.project (project_code, project_name)
            VALUES (%s, %s)
            RETURNING project_id
            """,
                (f"{code_prefix}_PROJECT", f"{code_prefix} Project"),
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
            VALUES (%s, %s, %s, %s, %s)
            RETURNING tenant_id
            """,
                (
                    project_id,
                    f"{code_prefix}_TENANT",
                    f"{code_prefix} Tenant",
                    code_prefix.lower(),
                    f"{code_prefix.lower()}_admin",
                ),
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
            VALUES (%s, %s, %s)
            RETURNING system_id
            """,
                (f"{code_prefix}_ERP", f"{code_prefix} ERP", system_type_id),
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
            VALUES (%s, %s, %s, %s, %s)
            RETURNING connection_id
            """,
                (
                    tenant_id,
                    system_id,
                    f"{code_prefix}_SOURCE",
                    f"{code_prefix} Source",
                    connection_type_id,
                ),
            ).fetchone(),
            "connection_id",
        )
        object_ids: list[int] = []
        for object_name, zone_code in (
            ("orders", "bronze"),
            ("customers", "bronze"),
            ("silver_orders", "silver"),
            ("gold_sales", "gold"),
        ):
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
                    (
                        connection_id,
                        object_name,
                        object_type_id,
                        zone_ids[zone_code],
                    ),
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
        principal = connection.execute(
            """
            SELECT principal_id
              FROM security.entra_principal_identity
             WHERE entra_tenant_id = %s
               AND entra_object_id = %s
            """,
            (ENTRA_TENANT_ID, ENTRA_OBJECT_ID),
        ).fetchone()
        if principal is None:
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
        else:
            principal_id = _required_id(principal, "principal_id")
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


@overload
def _replace_codes(
    value: dict[ModelChangeSetDataset, list[dict[str, object]]],
    *,
    code_prefix: str = "MODEL_TOOL",
) -> dict[ModelChangeSetDataset, list[dict[str, object]]]: ...


@overload
def _replace_codes(
    value: list[dict[str, object]],
    *,
    code_prefix: str = "MODEL_TOOL",
) -> list[dict[str, object]]: ...


@overload
def _replace_codes(
    value: object,
    *,
    code_prefix: str = "MODEL_TOOL",
) -> object: ...


def _replace_codes(value: object, *, code_prefix: str = "MODEL_TOOL") -> object:
    replacements = {
        "DEMO": f"{code_prefix}_TENANT",
        "ERP": f"{code_prefix}_ERP",
        "SOURCE": f"{code_prefix}_SOURCE",
    }
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        replaced_mapping: dict[object, object] = {
            key: _replace_codes(item, code_prefix=code_prefix)
            for key, item in mapping.items()
        }
        return replaced_mapping
    if isinstance(value, list):
        items = cast(list[object], value)
        replaced_items: list[object] = [
            _replace_codes(item, code_prefix=code_prefix) for item in items
        ]
        return replaced_items
    return value


def _snapshot_archive(content: bytes) -> tuple[dict[str, int], str]:
    assert content
    counts: dict[str, int] = {}
    serialized: list[str] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        manifest = json.loads(archive.read("model-snapshot/manifest.json"))
        assert manifest["snapshot_kind"] == "model"
        assert manifest["database_ids_included"] is False
        for definition in DATASETS:
            rows = archive.read(f"model-snapshot/{definition.rows_path}").decode(
                "utf-8"
            )
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
        assert "Optional: no" in dimensional


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
    inference_only = analysis.structured_content["from_relationships"][0]
    assert inference_only["validation_policy_version"] is None
    assert inference_only["validation_result"] is None
    assert inference_only["validation_duplicate_target_key_count"] is None
    dimensional_relationship = contents["get_model_dimensional_relationships"][
        "relationships"
    ][0]
    assert dimensional_relationship["dimensional_relationship_is_optional"] is False

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
    mapped_object_id = contents["get_model_object_mappings"]["mappings"][0]["object_id"]

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
            "get_model_dimensional_attributes",
            {"dimensional_entity_ids": [dimensional_entity_id]},
            "attributes",
        ),
        (
            "get_model_dimensional_relationships",
            {"dimensional_entity_ids": [dimensional_entity_id]},
            "relationships",
        ),
        (
            "get_model_object_mappings",
            {"object_ids": [mapped_object_id]},
            "mappings",
        ),
        (
            "get_model_attribute_mappings",
            {"object_ids": [mapped_object_id]},
            "mappings",
        ),
    )
    for tool_name, filters, collection in filtered_reads:
        result = await client.call_tool(
            tool_name,
            {"model_id": model_id, **filters},
        )
        assert result.is_error is False, tool_name
        assert result.structured_content is not None
        assert len(result.structured_content[collection]) == 1, tool_name

    filtered_analysis = await client.call_tool(
        "get_model_analysis",
        {"model_id": model_id, "object_ids": [object_id]},
    )
    assert filtered_analysis.is_error is False
    assert filtered_analysis.structured_content is not None
    assert len(filtered_analysis.structured_content["from_relationships"]) == 1
    assert len(filtered_analysis.structured_content["to_relationships"]) == 0
