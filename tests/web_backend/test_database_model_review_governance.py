"""Analysis review authority and concurrency on disposable PostgreSQL only."""

# pyright: reportPrivateUsage=false
import asyncio
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    TenantLockRequiredError,
    TenantWorkflowConflictError,
)
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.model_change_sets.contracts import (
    ReviewModelRecordsRequest,
)
from gds_workbench_api.features.model_change_sets.repository import (
    PostgresModelChangeSetRepository,
)
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
)
from psycopg.errors import InsufficientPrivilege
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import (
    CREATE_WORKFLOW_RUN_SQL,
    create_workflow_run_parameters,
    seed_workflow_context,
)

AUTHORIZE_SQL = "SELECT * FROM application.authorize_model_record_review(%s,%s,%s,%s,%s)"
AUTHORIZE_SIGNATURE = (
    "application.authorize_model_record_review(uuid,uuid,character varying,bigint,bigint)"
)


async def _wait_for_database_lock(database: DisposablePostgres, function: str) -> None:
    # Observe a real PostgreSQL wait; a slow pool connection must not pass the test.
    async with asyncio.timeout(3):
        while True:
            with database.connect_owner() as connection:
                waiting = require_row(
                    connection.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE datname=current_database() AND usename=%s "
                        "AND wait_event_type='Lock' AND position(%s IN query)>0) AS waiting",
                        (database.web_runtime_user, function),
                    ).fetchone()
                )["waiting"]
            if waiting:
                return
            await asyncio.sleep(0.01)


def _setup(database: DisposablePostgres):
    context = seed_workflow_context(database)
    with database.connect_owner() as connection:
        attributes = connection.execute(
            """INSERT INTO core.attribute (
                object_id,attribute_name,attribute_ordinal_position,attribute_data_type
            ) VALUES (%s,'review_child',1,'BIGINT'),(%s,'review_parent',2,'BIGINT')
            RETURNING attribute_id""",
            (context.selected_object_ids[0], context.selected_object_ids[0]),
        ).fetchall()
        result = require_row(
            connection.execute(
                """INSERT INTO workflow.analysis_result (
                    model_id,from_object_id,from_attribute_id,to_object_id,to_attribute_id,
                    relationship_kind,relationship_confidence,relationship_basis
                ) VALUES (%s,%s,%s,%s,%s,'reference','high','Fixture relationship')
                RETURNING analysis_result_id""",
                (
                    context.model_id,
                    context.selected_object_ids[0],
                    attributes[0]["attribute_id"],
                    context.selected_object_ids[0],
                    attributes[1]["attribute_id"],
                ),
            ).fetchone()
        )
        second_model = require_row(
            connection.execute(
                "INSERT INTO model.model(tenant_id,model_name) VALUES(%s,%s) "
                "RETURNING model_id,model_revision",
                (context.tenant_id, f"Concurrent review fixture {uuid4().hex}"),
            ).fetchone()
        )
        connection.execute(
            "INSERT INTO model.model_input_scope(model_id,object_id) "
            "SELECT %s,object_id FROM model.model_input_scope WHERE model_id=%s",
            (second_model["model_id"], context.model_id),
        )
        other_context = replace(
            context,
            model_id=second_model["model_id"],
            model_revision=second_model["model_revision"],
        )
        run = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(
                    other_context,
                    correlation_id=uuid4(),
                    workflow="profiling",
                    execution_mode=None,
                ),
            ).fetchone()
        )
    database_runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=3, pool_timeout_seconds=5
    )
    return (
        context,
        result["analysis_result_id"],
        other_context,
        run["workflow_run_id"],
        database_runtime,
    )


@pytest.mark.parametrize("start_first", [True, False])
async def test_review_serializes_with_other_model_workflow_start(
    web_postgres_database: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    start_first: bool,
) -> None:
    context, record_id, other_context, run_id, runtime = _setup(web_postgres_database)
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    service = DatabaseModelChangeSetService(database=runtime, authorizer=AuthorizationService())
    command = ReviewModelRecordsRequest(
        dataset="analysis_result",
        record_ids=[record_id],
        action="lock",
        expected_model_revision=context.model_revision,
    )
    entered = asyncio.Event()
    checked = asyncio.Event()
    release = asyncio.Event()
    original = PostgresModelChangeSetRepository.has_running_tenant_workflow

    async def pause_after_check(
        repository: PostgresModelChangeSetRepository, *, tenant_id: int
    ) -> bool:
        running = await original(repository, tenant_id=tenant_id)
        assert tenant_id == context.tenant_id and not running
        checked.set()
        await asyncio.wait_for(release.wait(), timeout=5)
        return running

    async def review():
        entered.set()
        return await service.review_records(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            command=command,
            idempotency_key=uuid4(),
        )

    async def start():
        async with runtime.write_transaction() as transaction:
            entered.set()
            return await transaction.fetch_one(
                "SELECT * FROM application.start_workflow_run(%s,%s,'user',%s,%s)",
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    run_id,
                    other_context.model_revision,
                ),
            )

    tasks: list[asyncio.Task[Any]] = []
    await runtime.open()
    try:
        if start_first:
            async with runtime.write_transaction() as transaction:
                started = await transaction.fetch_one(
                    "SELECT * FROM application.start_workflow_run(%s,%s,'user',%s,%s)",
                    (
                        context.entra_tenant_id,
                        context.entra_object_id,
                        run_id,
                        other_context.model_revision,
                    ),
                )
                assert started is not None and started["workflow_run_state"] == "running"
                competing = asyncio.create_task(review())
                tasks.append(competing)
                await asyncio.wait_for(entered.wait(), timeout=2)
                await _wait_for_database_lock(
                    web_postgres_database, "authorize_model_record_review"
                )
                assert not competing.done()
            with pytest.raises(TenantWorkflowConflictError):
                await asyncio.wait_for(competing, timeout=5)
        else:
            monkeypatch.setattr(
                PostgresModelChangeSetRepository,
                "has_running_tenant_workflow",
                pause_after_check,
            )
            reviewing = asyncio.create_task(review())
            tasks.append(reviewing)
            await asyncio.wait_for(checked.wait(), timeout=5)
            entered.clear()
            competing = asyncio.create_task(start())
            tasks.append(competing)
            await asyncio.wait_for(entered.wait(), timeout=2)
            await _wait_for_database_lock(web_postgres_database, "start_workflow_run")
            assert not competing.done()
            release.set()
            reviewed = await asyncio.wait_for(reviewing, timeout=5)
            assert reviewed.action_count == 1
            assert reviewed.model_revision == context.model_revision + 1
            started = await asyncio.wait_for(competing, timeout=5)
            assert started is not None and started["workflow_run_state"] == "running"
        with web_postgres_database.connect_owner() as connection:
            assert (
                require_row(
                    connection.execute(
                        (
                            "SELECT workflow_run_state FROM application.workflow_run WHERE "
                            "workflow_run_id=%s AND model_id=%s"
                        ),
                        (run_id, other_context.model_id),
                    ).fetchone()
                )["workflow_run_state"]
                == "running"
            )
            assert require_row(
                connection.execute(
                    (
                        "SELECT analysis_result_is_locked FROM workflow.analysis_result "
                        "WHERE analysis_result_id=%s AND model_id=%s"
                    ),
                    (record_id, context.model_id),
                ).fetchone()
            )["analysis_result_is_locked"] is (not start_first)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await runtime.close()


def test_web_role_cannot_lock_tenant_row_directly(
    web_postgres_database: DisposablePostgres,
) -> None:
    with web_postgres_database.connect_owner() as connection:
        privileges = require_row(
            connection.execute(
                "SELECT has_table_privilege('gds_web_write','security.tenant_lock','SELECT') "
                "AS can_read,has_any_column_privilege('gds_web_write',"
                "'security.tenant_lock','UPDATE') AS can_update"
            ).fetchone()
        )
        assert privileges == {"can_read": True, "can_update": False}
        with pytest.raises(InsufficientPrivilege), connection.transaction():
            connection.execute("SET LOCAL ROLE gds_web_write")
            connection.execute("SELECT tenant_id FROM security.tenant_lock FOR UPDATE")


@pytest.mark.parametrize("other_review", ["model", "metadata"])
async def test_review_serializes_with_other_governed_review(
    web_postgres_database: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    other_review: str,
) -> None:
    context, record_id, other_context, _, runtime = _setup(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        other_record_id = require_row(
            connection.execute(
                """INSERT INTO workflow.analysis_result(
                       model_id, from_object_id, from_attribute_id, to_object_id,
                       to_attribute_id, relationship_kind, relationship_confidence,
                       relationship_basis)
                   SELECT %s, from_object_id, from_attribute_id, to_object_id,
                          to_attribute_id, relationship_kind, relationship_confidence,
                          relationship_basis
                     FROM workflow.analysis_result
                    WHERE analysis_result_id=%s RETURNING analysis_result_id""",
                (other_context.model_id, record_id),
            ).fetchone()
        )["analysis_result_id"]
        object_selection = require_row(
            connection.execute(
                "SELECT object_id AS record_id,application.metadata_object_review_revision(object) "
                "AS expected_revision FROM core.object AS object WHERE object_id=%s",
                (context.selected_object_ids[0],),
            ).fetchone()
        )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    service = DatabaseModelChangeSetService(database=runtime, authorizer=AuthorizationService())
    checked = asyncio.Event()
    release = asyncio.Event()
    original = PostgresModelChangeSetRepository.has_running_tenant_workflow

    async def pause_first_review(
        repository: PostgresModelChangeSetRepository, *, tenant_id: int
    ) -> bool:
        running = await original(repository, tenant_id=tenant_id)
        if not checked.is_set():
            assert not running
            checked.set()
            await asyncio.wait_for(release.wait(), timeout=5)
        return running

    monkeypatch.setattr(
        PostgresModelChangeSetRepository,
        "has_running_tenant_workflow",
        pause_first_review,
    )

    async def competing_review():
        if other_review == "model":
            result = await service.review_records(
                principal,
                tenant_id=context.tenant_id,
                model_id=other_context.model_id,
                command=ReviewModelRecordsRequest(
                    dataset="analysis_result",
                    record_ids=[other_record_id],
                    action="lock",
                    expected_model_revision=other_context.model_revision,
                ),
                idempotency_key=uuid4(),
            )
            return result.action_count
        async with runtime.write_transaction() as transaction:
            result = require_row(
                await transaction.fetch_one(
                    (
                        "SELECT * FROM "
                        "application.review_metadata_records(%s,%s,'user',%s,'object','lock',%s,%s)"
                    ),
                    (
                        context.entra_tenant_id,
                        context.entra_object_id,
                        context.tenant_id,
                        Jsonb([object_selection]),
                        uuid4(),
                    ),
                )
            )
            assert result["denial_code"] is None
            return result["action_count"]

    tasks: list[asyncio.Task[Any]] = []
    await runtime.open()
    try:
        reviewing = asyncio.create_task(
            service.review_records(
                principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id,
                command=ReviewModelRecordsRequest(
                    dataset="analysis_result",
                    record_ids=[record_id],
                    action="lock",
                    expected_model_revision=context.model_revision,
                ),
                idempotency_key=uuid4(),
            )
        )
        tasks.append(reviewing)
        await asyncio.wait_for(checked.wait(), timeout=5)
        competing = asyncio.create_task(competing_review())
        tasks.append(competing)
        await _wait_for_database_lock(
            web_postgres_database,
            "authorize_model_record_review"
            if other_review == "model"
            else "review_metadata_records",
        )
        assert not competing.done()
        release.set()
        assert (await asyncio.wait_for(reviewing, timeout=5)).action_count == 1
        assert await asyncio.wait_for(competing, timeout=5) == 1
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await runtime.close()


async def test_committed_other_model_start_already_blocks_review(
    web_postgres_database: DisposablePostgres,
) -> None:
    context, record_id, other_context, run_id, runtime = _setup(web_postgres_database)
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    service = DatabaseModelChangeSetService(database=runtime, authorizer=AuthorizationService())
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            started = await transaction.fetch_one(
                "SELECT * FROM application.start_workflow_run(%s,%s,'user',%s,%s)",
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    run_id,
                    other_context.model_revision,
                ),
            )
            assert started is not None and started["workflow_run_state"] == "running"
        with pytest.raises(TenantWorkflowConflictError):
            await service.review_records(
                principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id,
                command=ReviewModelRecordsRequest(
                    dataset="analysis_result",
                    record_ids=[record_id],
                    action="lock",
                    expected_model_revision=context.model_revision,
                ),
                idempotency_key=uuid4(),
            )
    finally:
        await runtime.close()
    with web_postgres_database.connect_owner() as connection:
        assert (
            require_row(
                connection.execute(
                    "SELECT analysis_result_is_locked FROM workflow.analysis_result "
                    "WHERE analysis_result_id=%s",
                    (record_id,),
                ).fetchone()
            )["analysis_result_is_locked"]
            is False
        )


@pytest.mark.parametrize(
    ("scenario", "denial"),
    [
        ("authorized", None),
        ("invalid_tenant", "invalid_request"),
        ("invalid_model", "invalid_request"),
        ("missing_identity", "invalid_request"),
        ("service_principal", "authorization_denied"),
        ("unknown_identity", "authorization_denied"),
        ("inactive_identity", "authorization_denied"),
        ("inactive_model", "model_not_found"),
        ("foreign_model", "model_not_found"),
        ("unauthorized_tenant", "tenant_not_found"),
        ("inactive_tenant", "tenant_not_found"),
        ("reader", "authorization_denied"),
        ("expired_lock", "tenant_lock_required"),
        ("other_lock_owner", "tenant_locked"),
    ],
)
def test_review_helper_authority_and_denials_do_not_return_model_headers(
    web_postgres_database: DisposablePostgres, scenario: str, denial: str | None
) -> None:
    context = seed_workflow_context(web_postgres_database)
    parameters: list[Any] = [
        context.entra_tenant_id,
        context.entra_object_id,
        "user",
        context.tenant_id,
        context.model_id,
    ]
    with web_postgres_database.connect_owner() as connection:
        if scenario == "invalid_tenant":
            parameters[3] = 0
        elif scenario == "invalid_model":
            parameters[4] = 0
        elif scenario == "missing_identity":
            parameters[0] = None
        elif scenario == "service_principal":
            parameters[2] = "service_principal"
        elif scenario == "unknown_identity":
            parameters[1] = uuid4()
        elif scenario == "inactive_identity":
            connection.execute(
                (
                    "UPDATE security.entra_principal_identity SET is_active=FALSE WHERE "
                    "principal_id=%s"
                ),
                (context.principal_id,),
            )
        elif scenario == "inactive_model":
            connection.execute(
                "UPDATE model.model SET is_active=FALSE WHERE model_id=%s",
                (context.model_id,),
            )
        elif scenario in {"foreign_model", "unauthorized_tenant"}:
            foreign = seed_workflow_context(web_postgres_database)
            parameters[4] = foreign.model_id
            if scenario == "unauthorized_tenant":
                parameters[3] = foreign.tenant_id
        elif scenario == "inactive_tenant":
            connection.execute(
                "UPDATE core.tenant SET is_active=FALSE WHERE tenant_id=%s",
                (context.tenant_id,),
            )
        elif scenario == "reader":
            connection.execute(
                "UPDATE security.tenant_principal_access SET tenant_role='viewer' "
                "WHERE principal_id=%s AND tenant_id=%s",
                (context.principal_id, context.tenant_id),
            )
        elif scenario == "expired_lock":
            connection.execute(
                (
                    "UPDATE security.tenant_lock SET "
                    "tenant_lock_acquired_time=clock_timestamp()-interval '2 "
                    "minutes',tenant_lock_expires_time=clock_timestamp()-interval '1 minute' "
                    "WHERE tenant_id=%s"
                ),
                (context.tenant_id,),
            )
        elif scenario == "other_lock_owner":
            owner = require_row(
                connection.execute(
                    """INSERT INTO security.principal(
                           principal_type, principal_display_name, principal_email)
                       VALUES('user','Other fixture owner','other-owner@example.test')
                       RETURNING principal_id"""
                ).fetchone()
            )["principal_id"]
            connection.execute(
                "UPDATE security.tenant_lock SET locked_by_principal_id=%s WHERE tenant_id=%s",
                (owner, context.tenant_id),
            )
        before = require_row(
            connection.execute(
                "SELECT to_jsonb(target) AS model FROM model.model AS target WHERE model_id=%s",
                (context.model_id,),
            ).fetchone()
        )
        connection.execute("SET LOCAL ROLE gds_web_write")
        result = require_row(connection.execute(AUTHORIZE_SQL, parameters).fetchone())
        assert result["denial_code"] == denial
        if denial is None:
            assert result == {
                "denial_code": None,
                "principal_id": context.principal_id,
                "model_id": context.model_id,
                "tenant_id": context.tenant_id,
                "model_name": before["model"]["model_name"],
                "model_revision": context.model_revision,
            }
        else:
            assert all(value is None for key, value in result.items() if key != "denial_code")
        after = require_row(
            connection.execute(
                "SELECT to_jsonb(target) AS model FROM model.model AS target WHERE model_id=%s",
                (context.model_id,),
            ).fetchone()
        )
        assert after == before


def test_review_helper_is_web_only_and_preserves_tenant_lock_privileges(
    web_postgres_database: DisposablePostgres,
) -> None:
    with web_postgres_database.connect_owner() as connection:
        rows = connection.execute(
            "SELECT role,has_function_privilege(role,%s,'EXECUTE') AS can_review,"
            "has_any_column_privilege(role,'security.tenant_lock','UPDATE') AS can_update_lock "
            "FROM unnest(ARRAY['public','gds_app_write','gds_web_write',"
            "'gds_mcp_runtime','gds_notebook_runtime']) AS role ORDER BY role",
            (AUTHORIZE_SIGNATURE,),
        ).fetchall()
        assert [row["role"] for row in rows if row["can_review"]] == ["gds_web_write"]
        assert not any(row["can_update_lock"] for row in rows)
        contract = require_row(
            connection.execute(
                "SELECT prosecdef,provolatile,proconfig,pg_get_function_result(oid) AS result "
                "FROM pg_proc WHERE oid=to_regprocedure(%s)",
                (AUTHORIZE_SIGNATURE,),
            ).fetchone()
        )
        assert contract == {
            "prosecdef": True,
            "provolatile": "v",
            "proconfig": ["search_path=pg_catalog"],
            "result": "TABLE(denial_code character varying, principal_id bigint, model_id bigint, "
            "tenant_id bigint, model_name character varying, model_revision bigint)",
        }


async def test_review_helper_rechecks_lock_expiry_after_waiting(
    web_postgres_database: DisposablePostgres,
) -> None:
    context, _, _, _, runtime = _setup(web_postgres_database)
    entered = asyncio.Event()

    async def authorize():
        async with runtime.write_transaction() as transaction:
            entered.set()
            return await transaction.fetch_one(
                AUTHORIZE_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    "user",
                    context.tenant_id,
                    context.model_id,
                ),
            )

    task = None
    await runtime.open()
    try:
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "SELECT tenant_id FROM security.tenant_lock WHERE tenant_id=%s FOR UPDATE",
                (context.tenant_id,),
            )
            task = asyncio.create_task(authorize())
            await asyncio.wait_for(entered.wait(), timeout=2)
            await _wait_for_database_lock(web_postgres_database, "authorize_model_record_review")
            assert not task.done()
            connection.execute(
                (
                    "UPDATE security.tenant_lock SET "
                    "tenant_lock_acquired_time=clock_timestamp()-interval '2 "
                    "minutes',tenant_lock_expires_time=clock_timestamp()-interval '1 minute' "
                    "WHERE tenant_id=%s"
                ),
                (context.tenant_id,),
            )
        result = await asyncio.wait_for(task, timeout=5)
        assert result is not None and result["denial_code"] == "tenant_lock_required"
        assert result["principal_id"] is None and result["model_revision"] is None
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await runtime.close()


async def test_review_rechecks_expiry_after_graph_validation_before_mutation(
    web_postgres_database: DisposablePostgres, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, record_id, _, _, runtime = _setup(web_postgres_database)
    original = PostgresModelChangeSetRepository.read_analysis_review_records
    passed_initial_authorization = False

    async def pause_during_review(
        repository: PostgresModelChangeSetRepository,
        *,
        model_id: int,
        record_ids: list[int],
    ):
        nonlocal passed_initial_authorization
        rows = await original(repository, model_id=model_id, record_ids=record_ids)
        passed_initial_authorization = True
        await asyncio.sleep(2.1)
        return rows

    monkeypatch.setattr(
        PostgresModelChangeSetRepository,
        "read_analysis_review_records",
        pause_during_review,
    )
    service = DatabaseModelChangeSetService(database=runtime, authorizer=AuthorizationService())
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    await runtime.open()
    try:
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                (
                    "UPDATE security.tenant_lock SET "
                    "tenant_lock_expires_time=clock_timestamp()+interval '2 seconds' WHERE "
                    "tenant_id=%s"
                ),
                (context.tenant_id,),
            )
        with pytest.raises(TenantLockRequiredError):
            await service.review_records(
                principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id,
                command=ReviewModelRecordsRequest(
                    dataset="analysis_result",
                    record_ids=[record_id],
                    action="lock",
                    expected_model_revision=context.model_revision,
                ),
                idempotency_key=uuid4(),
            )
        assert passed_initial_authorization
        with web_postgres_database.connect_owner() as connection:
            state = require_row(
                connection.execute(
                    (
                        "SELECT "
                        "result.analysis_result_is_locked,model.model_revision,(SELECT "
                        "count(*) FROM mcp.model_change_set WHERE model_id=%s) AS "
                        "change_sets FROM workflow.analysis_result AS result JOIN "
                        "model.model AS model USING(model_id) WHERE "
                        "result.analysis_result_id=%s"
                    ),
                    (context.model_id, record_id),
                ).fetchone()
            )
            assert state == {
                "analysis_result_is_locked": False,
                "model_revision": context.model_revision,
                "change_sets": 0,
            }
    finally:
        await runtime.close()


async def test_authorized_review_replay_survives_other_model_start_but_requires_current_lock(
    web_postgres_database: DisposablePostgres,
) -> None:
    context, record_id, other_context, run_id, runtime = _setup(web_postgres_database)
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    service = DatabaseModelChangeSetService(database=runtime, authorizer=AuthorizationService())
    command = ReviewModelRecordsRequest(
        dataset="analysis_result",
        record_ids=[record_id],
        action="lock",
        expected_model_revision=context.model_revision,
    )
    key = uuid4()
    await runtime.open()
    try:
        reviewed = await service.review_records(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            command=command,
            idempotency_key=key,
        )
        async with runtime.write_transaction() as transaction:
            started = await transaction.fetch_one(
                "SELECT * FROM application.start_workflow_run(%s,%s,'user',%s,%s)",
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    run_id,
                    other_context.model_revision,
                ),
            )
            assert started is not None and started["workflow_run_state"] == "running"
        replay = await service.review_records(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            command=command,
            idempotency_key=key,
        )
        assert replay == reviewed
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                (
                    "UPDATE security.tenant_lock SET "
                    "tenant_lock_acquired_time=clock_timestamp()-interval '2 "
                    "minutes',tenant_lock_expires_time=clock_timestamp()-interval '1 minute' "
                    "WHERE tenant_id=%s"
                ),
                (context.tenant_id,),
            )
        with pytest.raises(TenantLockRequiredError):
            await service.review_records(
                principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id,
                command=command,
                idempotency_key=key,
            )
    finally:
        await runtime.close()
