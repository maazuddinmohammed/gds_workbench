"""Model lock fences every model-owned write; metadata and reads remain independent."""

# pyright: reportPrivateUsage=false
from dataclasses import replace
from uuid import uuid4

import pytest
from psycopg import errors, sql

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.application.change_sets.model_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import (
    ModelReadContext,
    authorize_model_read,
)
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.authorization import ActorKind
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.models.command_contracts import SetModelLockRequest
from gds_workbench_api.features.models.command_service import (
    DatabaseModelCommandService,
)
from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import complete_model_graph
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _seed_model_foundation,
    _replace_codes,
    _acquire_tenant_lock,
)


async def test_model_lock_fences_graph_and_runtime_but_keeps_reads_and_metadata(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    prefix = "MODEL_LOCK_" + uuid4().hex
    model_id, tenant_id = _seed_model_foundation(fixture, code_prefix=prefix)
    model = ModelReadContext(model_id, tenant_id, "Model Tool Round Trip", 1)
    runtime = fixture.create_runtime_adapter()
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            validation = validate_future_graph(
                snapshot=await build_model_snapshot(transaction, model),
                physical_scope=await load_model_physical_scope(transaction, model),
                staged_documents=_replace_codes(
                    complete_model_graph(), code_prefix=prefix
                ),
            )
            assert validation.valid
            await ModelMaterializer(transaction, model_id, "a" * 64).apply(
                validation.records
            )
    finally:
        await runtime.close()
    _acquire_tenant_lock(fixture, tenant_id)
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseModelCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    principal = StaticIdentityProvider().request_principal(None)
    await database.open()
    try:
        locked = await service.set_model_lock(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            request=SetModelLockRequest(expected_model_revision=1, is_locked=True),
        )
        assert locked.model_revision == 2
        async with database.read_transaction() as transaction:
            context = await authorize_model_read(
                transaction,
                authorizer=AuthorizationService(),
                principal=principal,
                model_id=model_id,
            )
            snapshot = await build_model_snapshot(transaction, context)
        assert context.is_locked and snapshot.is_locked
        assert (
            snapshot.logical.entities
            and snapshot.mapping.objects
            and snapshot.validation.checks
        )
        with fixture.connect_owner() as connection:
            tables = connection.execute("""
                SELECT namespace.nspname, relation.relname, attribute.attname
                FROM pg_class AS relation JOIN pg_namespace AS namespace ON namespace.oid=relation.relnamespace
                JOIN pg_attribute AS attribute ON attribute.attrelid=relation.oid
                WHERE namespace.nspname IN ('model','workflow','application','mcp')
                  AND relation.relkind='r' AND attribute.attname='model_id'
                  AND relation.relname <> 'model_lock_event'
                """).fetchall()
            checked = 0
            for table in tables:
                identifier = sql.Identifier(table["nspname"], table["relname"])
                count = connection.execute(
                    sql.SQL("SELECT count(*) AS n FROM {} WHERE model_id=%s").format(
                        identifier
                    ),
                    (model_id,),
                ).fetchone()
                if count is None or count["n"] == 0:
                    continue
                with (
                    pytest.raises(errors.ObjectNotInPrerequisiteState) as denied,
                    connection.transaction(),
                ):
                    column = sql.Identifier(
                        "updated_by"
                        if table["nspname"] == "model" and table["relname"] == "model"
                        else "model_id"
                    )
                    connection.execute(
                        sql.SQL("UPDATE {} SET {}={} WHERE model_id=%s").format(
                            identifier, column, column
                        ),
                        (model_id,),
                    )
                assert denied.value.diag.message_primary == "model_locked"
                checked += 1
            assert checked >= 25
            with (
                pytest.raises(errors.ObjectNotInPrerequisiteState),
                connection.transaction(),
            ):
                connection.execute(
                    "DELETE FROM workflow.mapping_object WHERE model_id=%s", (model_id,)
                )
            with (
                pytest.raises(errors.ObjectNotInPrerequisiteState),
                connection.transaction(),
            ):
                connection.execute(
                    "UPDATE workflow.validation_check SET is_active=is_active WHERE validation_group_id IN (SELECT validation_group_id FROM workflow.validation_group WHERE model_id=%s)",
                    (model_id,),
                )
            # Metadata remains writable independently of this Model.
            assert connection.execute(
                "UPDATE core.object SET value=%s::jsonb WHERE source_tenant_id=%s",
                ('{"independent":true}', tenant_id),
            ).rowcount > 0
            assert connection.execute(
                "SELECT is_locked FROM model.model WHERE model_id=%s", (model_id,)
            ).fetchone() == {"is_locked": True}
        with fixture.connect_runtime() as connection:
            assert connection.execute(
                "SELECT has_function_privilege(current_user, 'application.set_model_lock(uuid,uuid,bigint,bigint,bigint,boolean)', 'EXECUTE') AS allowed"
            ).fetchone() == {"allowed": False}
            with pytest.raises(errors.InsufficientPrivilege), connection.transaction():
                connection.execute(
                    "UPDATE model.model SET is_locked=FALSE WHERE model_id=%s",
                    (model_id,),
                )
        with pytest.raises(WorkbenchError) as denied:
            await service.set_model_lock(
                replace(principal, actor_kind=ActorKind.WORKLOAD),
                tenant_id=tenant_id,
                model_id=model_id,
                request=SetModelLockRequest(expected_model_revision=2, is_locked=False),
            )
        assert denied.value.code == "authorization_denied"
        with pytest.raises(WorkbenchError) as stale:
            await service.set_model_lock(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                request=SetModelLockRequest(expected_model_revision=1, is_locked=False),
            )
        assert stale.value.code == "model_revision_conflict"
        unlocked = await service.set_model_lock(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            request=SetModelLockRequest(expected_model_revision=2, is_locked=False),
        )
        assert unlocked.model_revision == 3
        with fixture.connect_owner() as connection:
            connection.execute(
                "UPDATE workflow.mapping_object SET model_id=model_id WHERE model_id=%s",
                (model_id,),
            )
            assert connection.execute(
                "SELECT is_locked, model_revision FROM model.model_lock_event WHERE model_id=%s ORDER BY model_lock_event_id",
                (model_id,),
            ).fetchall() == [
                {"is_locked": True, "model_revision": 2},
                {"is_locked": False, "model_revision": 3},
            ]
    finally:
        await database.close()


def test_model_lock_rejects_queued_work_and_locked_model_rejects_new_work(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    model_id, tenant_id = _seed_model_foundation(
        fixture, code_prefix="LOCK_WORK_" + uuid4().hex
    )
    with fixture.connect_owner() as connection:
        principal = connection.execute(
            "SELECT principal_id FROM security.tenant_principal_access WHERE tenant_id=%s",
            (tenant_id,),
        ).fetchone()
        assert principal is not None
        insert = """INSERT INTO application.workflow_run(tenant_id,model_id,model_revision,model_workflow,actor_principal_id,selected_scope_digest,selected_scope_count,correlation_id)
                    VALUES (%s,%s,1,'profiling',%s,%s,1,%s) RETURNING workflow_run_id"""
        row = connection.execute(
            insert, (tenant_id, model_id, principal["principal_id"], "a" * 64, uuid4())
        ).fetchone()
        assert row is not None
        with (
            pytest.raises(errors.ObjectNotInPrerequisiteState) as busy,
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE model.model SET is_locked=TRUE WHERE model_id=%s", (model_id,)
            )
        assert busy.value.diag.message_primary == "model_workflow_conflict"
        connection.execute(
            "UPDATE application.workflow_run SET workflow_run_state='cancelled', completed_time=clock_timestamp() WHERE workflow_run_id=%s",
            (row["workflow_run_id"],),
        )
        connection.execute(
            "UPDATE model.model SET is_locked=TRUE WHERE model_id=%s", (model_id,)
        )
        with (
            pytest.raises(errors.ObjectNotInPrerequisiteState) as denied,
            connection.transaction(),
        ):
            connection.execute(
                insert,
                (tenant_id, model_id, principal["principal_id"], "a" * 64, uuid4()),
            )
        assert denied.value.diag.message_primary == "model_locked"


async def test_locked_model_mcp_reads_work_but_change_set_mutations_fail(
    web_postgres_database: DisposablePostgres,
) -> None:
    from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
    from gds_etl_workbench.tools.change_sets.model import (
        register_model_change_set_tools,
    )
    from mcp import Client
    from mcp.server.mcpserver import MCPServer
    from mcp.types import TextContent

    fixture = web_postgres_database
    model_id, tenant_id = _seed_model_foundation(
        fixture, code_prefix="LOCK_MCP_" + uuid4().hex
    )
    _acquire_tenant_lock(fixture, tenant_id)
    database = fixture.create_runtime_adapter()
    identity = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database, identity_provider=identity, authorizer=authorizer
    )
    server = MCPServer[None](name="model-lock-test", middleware=[audit])
    register_model_change_set_tools(
        server,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
    )
    await database.open()
    try:
        async with Client(server) as client:
            created = await client.call_tool(
                "create_model_change_set", {"model_id": model_id}
            )
            assert not created.is_error
            change_set_id = created.structured_content["model_change_set_id"]
            with fixture.connect_owner() as connection:
                connection.execute(
                    "UPDATE mcp.model_change_set SET created_time=clock_timestamp()-interval '3 hours', last_activity_time=clock_timestamp()-interval '2 hours', expires_time=clock_timestamp()-interval '1 hour' WHERE model_change_set_id=%s",
                    (change_set_id,),
                )
                connection.execute(
                    "UPDATE model.model SET is_locked=TRUE WHERE model_id=%s",
                    (model_id,),
                )
            request = {"model_id": model_id, "model_change_set_id": change_set_id}
            for name in ("get_model_change_set", "get_model_change_set_fingerprint"):
                result = await client.call_tool(name, request)
                assert not result.is_error
            for name in (
                "validate_model_change_set",
                "apply_model_change_set",
                "archive_model_change_set",
            ):
                result = await client.call_tool(
                    name, {**request, "expected_draft_revision": 1}
                )
                assert result.is_error
                assert any(
                    isinstance(block, TextContent) and "model_locked:" in block.text
                    for block in result.content
                )
            result = await client.call_tool(
                "create_model_change_set", {"model_id": model_id}
            )
            assert result.is_error
            assert all(
                "model_lock" not in tool.name
                for tool in (await client.list_tools()).tools
            )
            with fixture.connect_owner() as connection:
                assert connection.execute(
                    "SELECT model_change_set_status FROM mcp.model_change_set WHERE model_change_set_id=%s",
                    (change_set_id,),
                ).fetchone() == {"model_change_set_status": "active"}
    finally:
        await database.close()


def test_lock_transition_serializes_with_an_in_flight_model_write(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    model_id, tenant_id = _seed_model_foundation(
        fixture, code_prefix="LOCK_RACE_" + uuid4().hex
    )
    with fixture.connect_owner() as writer, fixture.connect_owner() as locker:
        writer.execute(
            "INSERT INTO model.model_input_scope(model_id, object_id) SELECT %s, object_id FROM core.object WHERE source_tenant_id=%s LIMIT 1",
            (model_id, tenant_id),
        )
        with pytest.raises(errors.LockNotAvailable), locker.transaction():
            locker.execute("SET LOCAL lock_timeout='100ms'")
            locker.execute(
                "UPDATE model.model SET is_locked=TRUE WHERE model_id=%s", (model_id,)
            )
        writer.commit()
        locker.execute(
            "UPDATE model.model SET is_locked=TRUE WHERE model_id=%s", (model_id,)
        )
        assert locker.execute(
            "SELECT is_locked FROM model.model WHERE model_id=%s", (model_id,)
        ).fetchone() == {"is_locked": True}
