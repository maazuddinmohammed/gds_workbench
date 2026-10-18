"""Project lock fences every project-owned write; metadata and reads remain independent."""

# pyright: reportPrivateUsage=false
from dataclasses import replace
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.project import (
    load_project_physical_scope,
)
from gds_etl_workbench.application.change_sets.project_apply import ProjectMaterializer
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.project_read import (
    ProjectReadContext,
    authorize_project_read,
)
from gds_etl_workbench.application.project_snapshot import build_project_snapshot
from gds_etl_workbench.domain.authorization import ActorKind
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.projects.command_contracts import SetProjectLockRequest
from gds_workbench_api.features.projects.command_service import (
    DatabaseProjectCommandService,
)
from psycopg import errors, sql

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.project_test_fixtures import complete_project_graph
from tests.mcp.test_database_project_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _replace_codes,
    _seed_project_foundation,
)


async def test_project_lock_fences_graph_and_runtime_but_keeps_reads_and_metadata(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    prefix = "PROJECT_LOCK_" + uuid4().hex
    project_id, tenant_id = _seed_project_foundation(fixture, code_prefix=prefix)
    project = ProjectReadContext(project_id, tenant_id, "Project Tool Round Trip", 1)
    runtime = fixture.create_runtime_adapter()
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            validation = validate_future_graph(
                snapshot=await build_project_snapshot(transaction, project),
                physical_scope=await load_project_physical_scope(transaction, project),
                staged_documents=_replace_codes(
                    complete_project_graph(), code_prefix=prefix
                ),
            )
            assert validation.valid
            await ProjectMaterializer(transaction, project_id, "a" * 64).apply(
                validation.records
            )
    finally:
        await runtime.close()
    _acquire_tenant_lock(fixture, tenant_id)
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseProjectCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    principal = StaticIdentityProvider().request_principal(None)
    await database.open()
    try:
        locked = await service.set_project_lock(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            request=SetProjectLockRequest(expected_project_revision=1, is_locked=True),
        )
        assert locked.project_revision == 2
        async with database.read_transaction() as transaction:
            context = await authorize_project_read(
                transaction,
                authorizer=AuthorizationService(),
                principal=principal,
                project_id=project_id,
            )
            snapshot = await build_project_snapshot(transaction, context)
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
                WHERE namespace.nspname IN ('project','workflow','application','mcp')
                  AND relation.relkind='r' AND attribute.attname='project_id'
                  AND relation.relname <> 'project_lock_event'
                """).fetchall()
            checked = 0
            for table in tables:
                identifier = sql.Identifier(table["nspname"], table["relname"])
                count = connection.execute(
                    sql.SQL("SELECT count(*) AS n FROM {} WHERE project_id=%s").format(
                        identifier
                    ),
                    (project_id,),
                ).fetchone()
                if count is None or count["n"] == 0:
                    continue
                with (
                    pytest.raises(errors.ObjectNotInPrerequisiteState) as denied,
                    connection.transaction(),
                ):
                    column = sql.Identifier(
                        "updated_by"
                        if table["nspname"] == "project"
                        and table["relname"] == "project"
                        else "project_id"
                    )
                    connection.execute(
                        sql.SQL("UPDATE {} SET {}={} WHERE project_id=%s").format(
                            identifier, column, column
                        ),
                        (project_id,),
                    )
                assert denied.value.diag.message_primary == "project_locked"
                checked += 1
            assert checked >= 25
            with (
                pytest.raises(errors.ObjectNotInPrerequisiteState),
                connection.transaction(),
            ):
                connection.execute(
                    "DELETE FROM workflow.mapping_object WHERE project_id=%s",
                    (project_id,),
                )
            with (
                pytest.raises(errors.ObjectNotInPrerequisiteState),
                connection.transaction(),
            ):
                connection.execute(
                    "UPDATE workflow.validation_check SET is_active=is_active WHERE validation_group_id IN (SELECT validation_group_id FROM workflow.validation_group WHERE project_id=%s)",
                    (project_id,),
                )
            # Metadata remains writable independently of this Project.
            assert (
                connection.execute(
                    "UPDATE core.object SET value=%s::jsonb WHERE source_tenant_id=%s",
                    ('{"independent":true}', tenant_id),
                ).rowcount
                > 0
            )
            assert connection.execute(
                "SELECT is_locked FROM project.project WHERE project_id=%s",
                (project_id,),
            ).fetchone() == {"is_locked": True}
        with fixture.connect_runtime() as connection:
            assert connection.execute(
                "SELECT has_function_privilege(current_user, 'application.set_project_lock(uuid,uuid,bigint,bigint,bigint,boolean)', 'EXECUTE') AS allowed"
            ).fetchone() == {"allowed": False}
            with pytest.raises(errors.InsufficientPrivilege), connection.transaction():
                connection.execute(
                    "UPDATE project.project SET is_locked=FALSE WHERE project_id=%s",
                    (project_id,),
                )
        with pytest.raises(WorkbenchError) as denied:
            await service.set_project_lock(
                replace(principal, actor_kind=ActorKind.WORKLOAD),
                tenant_id=tenant_id,
                project_id=project_id,
                request=SetProjectLockRequest(
                    expected_project_revision=2, is_locked=False
                ),
            )
        assert denied.value.code == "authorization_denied"
        with pytest.raises(WorkbenchError) as stale:
            await service.set_project_lock(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                request=SetProjectLockRequest(
                    expected_project_revision=1, is_locked=False
                ),
            )
        assert stale.value.code == "project_revision_conflict"
        unlocked = await service.set_project_lock(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            request=SetProjectLockRequest(expected_project_revision=2, is_locked=False),
        )
        assert unlocked.project_revision == 3
        with fixture.connect_owner() as connection:
            connection.execute(
                "UPDATE workflow.mapping_object SET project_id=project_id WHERE project_id=%s",
                (project_id,),
            )
            assert connection.execute(
                "SELECT is_locked, project_revision FROM project.project_lock_event WHERE project_id=%s ORDER BY project_lock_event_id",
                (project_id,),
            ).fetchall() == [
                {"is_locked": True, "project_revision": 2},
                {"is_locked": False, "project_revision": 3},
            ]
    finally:
        await database.close()


def test_project_lock_rejects_queued_work_and_locked_project_rejects_new_work(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    project_id, tenant_id = _seed_project_foundation(
        fixture, code_prefix="LOCK_WORK_" + uuid4().hex
    )
    with fixture.connect_owner() as connection:
        principal = connection.execute(
            "SELECT principal_id FROM security.tenant_principal_access WHERE tenant_id=%s",
            (tenant_id,),
        ).fetchone()
        assert principal is not None
        insert = """INSERT INTO application.workflow_run(tenant_id,project_id,project_revision,project_workflow,actor_principal_id,selected_scope_digest,selected_scope_count,correlation_id)
                    VALUES (%s,%s,1,'profiling',%s,%s,1,%s) RETURNING workflow_run_id"""
        row = connection.execute(
            insert,
            (tenant_id, project_id, principal["principal_id"], "a" * 64, uuid4()),
        ).fetchone()
        assert row is not None
        with (
            pytest.raises(errors.ObjectNotInPrerequisiteState) as busy,
            connection.transaction(),
        ):
            connection.execute(
                "UPDATE project.project SET is_locked=TRUE WHERE project_id=%s",
                (project_id,),
            )
        assert busy.value.diag.message_primary == "project_workflow_conflict"
        connection.execute(
            "UPDATE application.workflow_run SET workflow_run_state='cancelled', completed_time=clock_timestamp() WHERE workflow_run_id=%s",
            (row["workflow_run_id"],),
        )
        connection.execute(
            "UPDATE project.project SET is_locked=TRUE WHERE project_id=%s",
            (project_id,),
        )
        with (
            pytest.raises(errors.ObjectNotInPrerequisiteState) as denied,
            connection.transaction(),
        ):
            connection.execute(
                insert,
                (tenant_id, project_id, principal["principal_id"], "a" * 64, uuid4()),
            )
        assert denied.value.diag.message_primary == "project_locked"


async def test_locked_project_mcp_reads_work_but_change_set_mutations_fail(
    web_postgres_database: DisposablePostgres,
) -> None:
    from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
    from gds_etl_workbench.tools.change_sets.project import (
        register_project_change_set_tools,
    )
    from mcp import Client
    from mcp.server.mcpserver import MCPServer
    from mcp.types import TextContent

    fixture = web_postgres_database
    project_id, tenant_id = _seed_project_foundation(
        fixture, code_prefix="LOCK_MCP_" + uuid4().hex
    )
    _acquire_tenant_lock(fixture, tenant_id)
    database = fixture.create_runtime_adapter()
    identity = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database, identity_provider=identity, authorizer=authorizer
    )
    server = MCPServer[None](name="project-lock-test", middleware=[audit])
    register_project_change_set_tools(
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
                "create_project_change_set", {"project_id": project_id}
            )
            assert not created.is_error
            change_set_id = created.structured_content["project_change_set_id"]
            with fixture.connect_owner() as connection:
                connection.execute(
                    "UPDATE mcp.project_change_set SET created_time=clock_timestamp()-interval '3 hours', last_activity_time=clock_timestamp()-interval '2 hours', expires_time=clock_timestamp()-interval '1 hour' WHERE project_change_set_id=%s",
                    (change_set_id,),
                )
                connection.execute(
                    "UPDATE project.project SET is_locked=TRUE WHERE project_id=%s",
                    (project_id,),
                )
            request = {"project_id": project_id, "project_change_set_id": change_set_id}
            for name in (
                "get_project_change_set",
                "get_project_change_set_fingerprint",
            ):
                result = await client.call_tool(name, request)
                assert not result.is_error
            for name in (
                "validate_project_change_set",
                "apply_project_change_set",
                "archive_project_change_set",
            ):
                result = await client.call_tool(
                    name, {**request, "expected_draft_revision": 1}
                )
                assert result.is_error
                assert any(
                    isinstance(block, TextContent) and "project_locked:" in block.text
                    for block in result.content
                )
            result = await client.call_tool(
                "create_project_change_set", {"project_id": project_id}
            )
            assert result.is_error
            assert all(
                "project_lock" not in tool.name
                for tool in (await client.list_tools()).tools
            )
            with fixture.connect_owner() as connection:
                assert connection.execute(
                    "SELECT project_change_set_status FROM mcp.project_change_set WHERE project_change_set_id=%s",
                    (change_set_id,),
                ).fetchone() == {"project_change_set_status": "active"}
    finally:
        await database.close()


def test_lock_transition_serializes_with_an_in_flight_project_write(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    project_id, tenant_id = _seed_project_foundation(
        fixture, code_prefix="LOCK_RACE_" + uuid4().hex
    )
    with fixture.connect_owner() as writer, fixture.connect_owner() as locker:
        writer.execute(
            "INSERT INTO project.project_input_scope(project_id, object_id) SELECT %s, object_id FROM core.object WHERE source_tenant_id=%s LIMIT 1",
            (project_id, tenant_id),
        )
        with pytest.raises(errors.LockNotAvailable), locker.transaction():
            locker.execute("SET LOCAL lock_timeout='100ms'")
            locker.execute(
                "UPDATE project.project SET is_locked=TRUE WHERE project_id=%s",
                (project_id,),
            )
        writer.commit()
        locker.execute(
            "UPDATE project.project SET is_locked=TRUE WHERE project_id=%s",
            (project_id,),
        )
        assert locker.execute(
            "SELECT is_locked FROM project.project WHERE project_id=%s", (project_id,)
        ).fetchone() == {"is_locked": True}
