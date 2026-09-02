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
from tests.mcp.model_test_fixtures import (
    complete_model_graph,
)

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.modeling_records import (
    ANALYSIS_VALIDATION_FIELDS,
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
from gds_etl_workbench.tools.modeling.model_details import register_list_models_tool
from gds_etl_workbench.tools.modeling.model_input_scope import (
    register_get_model_input_scope_tool,
)
from gds_etl_workbench.tools.modeling.read_model_section import (
    register_read_model_section_tool,
)
from gds_etl_workbench.tools.snapshots.archive import SnapshotArchive
from gds_etl_workbench.tools.snapshots.dbml.get_model_dbml import (
    register_export_model_dbml_tool,
)
from gds_etl_workbench.tools.snapshots.model.contracts import (
    DATASETS,
    ModelChangeSetDataset,
)
from gds_etl_workbench.tools.snapshots.model.get_model_snapshot import (
    register_create_model_snapshot_tool,
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
        complete_model_graph()["conceptual_object"][0],
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
        complete_model_graph()["conceptual_object"][0],
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
    staged = _replace_codes(complete_model_graph(), code_prefix="MODEL_BATCH")
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
            assert validated.structured_content["valid"] is True, (
                validated.structured_content
            )
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
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": "FragmentedCode",
        "artifact_name": "FragmentedCode.sql",
        "artifact_type": "sql_file",
        "generated_code_content": content,
        "generated_code_status": "active",
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
    staged = _replace_codes(complete_model_graph())
    for field in ANALYSIS_VALIDATION_FIELDS:
        staged["analysis_result"][0].pop(field)
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
    register_list_models_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    register_get_model_input_scope_tool(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    register_create_model_snapshot_tool(
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
    register_export_model_dbml_tool(
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
    register_read_model_section_tool(
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
                "list_models",
                {"tenant_id": tenant_id},
            )
            assert model_details.is_error is False
            returned_model = next(
                model
                for model in model_details.structured_content["models"]
                if model["model_id"] == model_id
            )
            assert returned_model["model_name"] == "Model Tool Round Trip"
            assert returned_model["model_input_scope_object_count"] == 0
            initial_scope = await client.call_tool(
                "get_model_input_scope",
                {"model_id": model_id},
            )
            assert initial_scope.is_error is False
            assert initial_scope.structured_content["object_count"] == 0
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
            assert len(validated.structured_content["action_review"]) == len(staged)
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
                "create_model_snapshot",
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
                "export_model_dbml",
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
            active_scope = await client.call_tool(
                "get_model_input_scope",
                {"model_id": model_id},
            )
            assert active_scope.is_error is False
            assert active_scope.structured_content["object_count"] == 3
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
            non_bronze_profile.update(
                {
                    "tenant_code": "MODEL_TOOL_GDS",
                    "system_code": "MODEL_TOOL_GDS",
                    "connection_code": "MODEL_TOOL_LAKEHOUSE",
                    "object_schema": "silver",
                    "object_name": "Order",
                    "attribute_name": "CustomerID",
                }
            )
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
            assert invalid_validation.structured_content["phase"] == "model_input_scope"
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
    assert action_count > 0
    assert snapshot_counts == {
        "model_details": 1,
        "model_input_scope": 3,
        "profiling_profile": 1,
        "analysis_result": 1,
        "modeling_assertion_document": 1,
        "modeling_assertion_record": 1,
        "conceptual_object": 2,
        "conceptual_relationship": 1,
        "logical_submodel": 1,
        "logical_entity": 2,
        "logical_attribute": 3,
        "logical_relationship": 1,
        "dimensional_submodel": 1,
        "dimensional_entity": 2,
        "dimensional_attribute": 3,
        "dimensional_relationship": 1,
        "model_object_binding": 4,
        "model_attribute_binding": 6,
        "mapping_dependency": 1,
        "mapping_object": 1,
        "mapping_attribute": 2,
        "generated_code": 1,
        "generated_code_source_system": 1,
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
    assert '"artifact_name":"Order.sql"' in serialized
    assert '"mapping_transformation_document":{' in serialized
    assert '"mapping_context_digest"' not in serialized
    assert '"source_context_digest"' not in serialized
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
        for zone_code in ("source", "bronze", "silver", "gold"):
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
        gds_tenant_id = _required_id(
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
                    f"{code_prefix}_GDS",
                    f"{code_prefix} GDS",
                    f"{code_prefix.lower()}_gds",
                    f"{code_prefix.lower()}_gds_admin",
                ),
            ).fetchone(),
            "tenant_id",
        )
        source_system_id = _required_id(
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
        gds_system_id = _required_id(
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
                (f"{code_prefix}_GDS", f"{code_prefix} GDS", system_type_id),
            ).fetchone(),
            "system_id",
        )
        source_connection_id = _required_id(
            connection.execute(
                """
            INSERT INTO core.connection (
                tenant_id,
                system_id,
                connection_code,
                connection_name,
                connection_type_id,
                has_foreign_catalog,
                foreign_catalog
            )
            VALUES (%s, %s, %s, %s, %s, TRUE, %s)
            RETURNING connection_id
            """,
                (
                    tenant_id,
                    source_system_id,
                    f"{code_prefix}_FC",
                    f"{code_prefix} Foreign Catalog",
                    connection_type_id,
                    f"{code_prefix.lower()}_foreign",
                ),
            ).fetchone(),
            "connection_id",
        )
        gds_connection_id = _required_id(
            connection.execute(
                """
            INSERT INTO core.connection (
                tenant_id,
                system_id,
                connection_code,
                connection_name,
                connection_type_id,
                is_global_data_store
            )
            VALUES (%s, %s, %s, %s, %s, TRUE)
            RETURNING connection_id
            """,
                (
                    gds_tenant_id,
                    gds_system_id,
                    f"{code_prefix}_LAKEHOUSE",
                    f"{code_prefix} Lakehouse",
                    connection_type_id,
                ),
            ).fetchone(),
            "connection_id",
        )
        physical_objects = (
            (
                source_connection_id,
                "src",
                "orders",
                "source",
                ("order_id", "customer_id"),
            ),
            (source_connection_id, "src", "customers", "source", ("customer_id",)),
            (gds_connection_id, "bronze", "orders", "bronze", ("customer_id",)),
            (gds_connection_id, "silver", "Order", "silver", ("OrderID", "CustomerID")),
            (gds_connection_id, "silver", "Customer", "silver", ("CustomerID",)),
            (
                gds_connection_id,
                "gold",
                "SalesFact",
                "gold",
                ("SalesKey", "CustomerKey"),
            ),
            (gds_connection_id, "gold", "CustomerDimension", "gold", ("CustomerKey",)),
        )
        for (
            physical_connection_id,
            object_schema,
            object_name,
            zone_code,
            attribute_names,
        ) in physical_objects:
            object_id = _required_id(
                connection.execute(
                    """
                INSERT INTO core.object (
                    connection_id,
                    source_tenant_id,
                    object_schema,
                    object_name,
                    object_type_id,
                    zone_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING object_id
                """,
                    (
                        physical_connection_id,
                        tenant_id,
                        object_schema,
                        object_name,
                        object_type_id,
                        zone_ids[zone_code],
                    ),
                ).fetchone(),
                "object_id",
            )
            for ordinal, attribute_name in enumerate(attribute_names, start=1):
                connection.execute(
                    """
                INSERT INTO core.attribute (
                    object_id,
                    attribute_name,
                    attribute_ordinal_position,
                    attribute_data_type,
                    attribute_nullability
                )
                VALUES (%s, %s, %s, 'bigint', FALSE)
                """,
                    (object_id, attribute_name, ordinal),
                )
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
        "TENANT-A": f"{code_prefix}_TENANT",
        "ERP": f"{code_prefix}_ERP",
        "FC": f"{code_prefix}_FC",
        "GDS": f"{code_prefix}_GDS",
        "LAKEHOUSE": f"{code_prefix}_LAKEHOUSE",
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
            "model-dbml/files/dimensional_salesmart.dbml",
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
        assert 'Table "SalesFact"' in dimensional
        assert "Ref dimensional_relationship_1:" in dimensional
        assert "Optional: no" in dimensional


async def _assert_focused_reads(client: Client, model_id: int) -> None:
    expected_counts = {
        "profiling_profile": 1,
        "analysis_result": 1,
        "modeling_assertion_document": 1,
        "modeling_assertion_record": 1,
        "conceptual_object": 2,
        "conceptual_relationship": 1,
        "logical_submodel": 1,
        "logical_entity": 2,
        "logical_attribute": 3,
        "logical_relationship": 1,
        "dimensional_submodel": 1,
        "dimensional_entity": 2,
        "dimensional_attribute": 3,
        "dimensional_relationship": 1,
        "model_object_binding": 4,
        "model_attribute_binding": 6,
        "mapping_dependency": 1,
        "mapping_object": 1,
        "mapping_attribute": 2,
    }
    for dataset, expected_count in expected_counts.items():
        result = await client.call_tool(
            "read_model_section",
            {"model_id": model_id, "dataset": dataset, "page_size": 50},
        )
        assert result.is_error is False, dataset
        assert result.structured_content is not None
        assert result.structured_content["dataset"] == dataset
        assert len(result.structured_content["records"]) == expected_count
        assert result.structured_content["next_cursor"] is None
