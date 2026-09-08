"""Physical review governance on fixture-created disposable PostgreSQL only."""

# pyright: reportPrivateUsage=false
import asyncio
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from gds_workbench_api.database import WebPostgresDatabase
from psycopg.errors import RaiseException
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import (
    CREATE_WORKFLOW_RUN_SQL,
    WorkflowContext,
    create_workflow_run_parameters,
    seed_workflow_context,
)

REVIEW_SQL = "SELECT * FROM application.review_metadata_records(%s,%s,%s,%s,%s,%s,%s,%s)"


def _setup(database: DisposablePostgres):
    context = seed_workflow_context(database)
    with database.connect_owner() as connection:
        attributes = tuple(
            require_row(
                connection.execute(
                    "INSERT INTO core.attribute("
                    "object_id,attribute_name,attribute_ordinal_position,"
                    "attribute_data_type,attribute_description) VALUES(%s,'review_attribute',1,"
                    "'STRING','Preserve this description') RETURNING attribute_id",
                    (object_id,),
                ).fetchone()
            )["attribute_id"]
            for object_id in context.selected_object_ids
        )
    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=3, pool_timeout_seconds=5
    )
    return context, attributes, runtime


def _selection(database: DisposablePostgres, record_type: str, ids: tuple[int, ...]):
    with database.connect_owner() as connection:
        if record_type == "object":
            return connection.execute(
                "SELECT object_id AS record_id,application.metadata_object_review_revision(object) "
                "AS expected_revision FROM core.object AS object "
                "WHERE object_id=ANY(%s) ORDER BY object_id",
                (list(ids),),
            ).fetchall()
        return connection.execute(
            "SELECT attribute_id AS record_id,"
            "application.metadata_attribute_review_revision(attribute,object) AS expected_revision "
            "FROM core.attribute AS attribute JOIN core.object AS object USING(object_id) "
            "WHERE attribute_id=ANY(%s) ORDER BY attribute_id",
            (list(ids),),
        ).fetchall()


async def _review(
    runtime: WebPostgresDatabase,
    context: WorkflowContext,
    record_type: str,
    action: str,
    records: object,
    *,
    key: UUID | None = None,
    principal_type: str = "user",
) -> dict[str, Any]:
    async with runtime.write_transaction() as transaction:
        return require_row(
            await transaction.fetch_one(
                REVIEW_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    principal_type,
                    context.tenant_id,
                    record_type,
                    action,
                    Jsonb(records),
                    key or uuid4(),
                ),
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", ["object", "attribute"])
async def test_review_no_op_and_sorted_idempotency_are_audited_without_changing_timestamps(
    web_postgres_database: DisposablePostgres,
    record_type: str,
) -> None:
    context, attributes, runtime = _setup(web_postgres_database)
    ids = context.selected_object_ids if record_type == "object" else attributes
    selection = _selection(web_postgres_database, record_type, ids)
    key = uuid4()
    await runtime.open()
    try:
        result = await _review(runtime, context, record_type, "reactivate", selection, key=key)
        assert result["denial_code"] is None and result["action_count"] == 0
        assert _selection(web_postgres_database, record_type, ids) == selection
        assert (
            await _review(runtime, context, record_type, "reactivate", selection[::-1], key=key)
            == result
        )
        conflict = await _review(runtime, context, record_type, "deactivate", selection, key=key)
        assert conflict["denial_code"] == "metadata_review_conflict"
        locked = await _review(runtime, context, record_type, "lock", selection)
        assert locked["action_count"] == len(ids)
        fresh = _selection(web_postgres_database, record_type, ids)
        repeated = await _review(runtime, context, record_type, "lock", fresh)
        assert repeated["denial_code"] is None and repeated["action_count"] == 0
        assert _selection(web_postgres_database, record_type, ids) == fresh
    finally:
        await runtime.close()
    with web_postgres_database.connect_owner() as connection:
        events = connection.execute(
            "SELECT action,action_count,before_records,records "
            "FROM application.metadata_review_event "
            "WHERE tenant_id=%s ORDER BY metadata_review_event_id",
            (context.tenant_id,),
        ).fetchall()
    assert len(events) == 3
    assert events[0]["action_count"] == events[2]["action_count"] == 0
    assert all(
        set(row) == {"record_id", "is_active", "is_locked"} for row in events[0]["before_records"]
    )
    assert all(
        set(row) == {"record_id", "is_active", "is_locked", "review_revision"}
        for row in events[0]["records"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", ["object", "attribute"])
@pytest.mark.parametrize("failure", ["foreign", "stale", "locked"])
async def test_complete_selection_is_validated_before_any_row_changes(
    web_postgres_database: DisposablePostgres,
    record_type: str,
    failure: str,
) -> None:
    context, attributes, runtime = _setup(web_postgres_database)
    ids = context.selected_object_ids if record_type == "object" else attributes
    selection = _selection(web_postgres_database, record_type, ids)
    expected = "metadata_selection_conflict"
    if failure == "foreign":
        other, other_attributes, other_runtime = _setup(web_postgres_database)
        foreign_ids = other.selected_object_ids if record_type == "object" else other_attributes
        selection += _selection(web_postgres_database, record_type, foreign_ids[:1])
        await other_runtime.close()
    elif failure == "stale":
        selection[-1]["expected_revision"] = "0" * 64
        expected = "metadata_revision_conflict"
    else:
        with web_postgres_database.connect_owner() as connection:
            if record_type == "object":
                connection.execute(
                    "UPDATE core.object SET is_locked=TRUE WHERE object_id=%s", (ids[-1],)
                )
            else:
                connection.execute(
                    "UPDATE core.attribute SET is_locked=TRUE WHERE attribute_id=%s", (ids[-1],)
                )
        selection = _selection(web_postgres_database, record_type, ids)
        expected = f"{record_type}_locked"
    before = _selection(web_postgres_database, record_type, ids)
    await runtime.open()
    try:
        denied = await _review(runtime, context, record_type, "deactivate", selection)
        assert denied == {
            "denial_code": expected,
            "review_event_id": None,
            "action_count": None,
            "records": None,
        }
    finally:
        await runtime.close()
    assert _selection(web_postgres_database, record_type, ids) == before
    with web_postgres_database.connect_owner() as connection:
        assert (
            require_row(
                connection.execute(
                    "SELECT count(*) AS n FROM application.metadata_review_event "
                    "WHERE tenant_id=%s",
                    (context.tenant_id,),
                ).fetchone()
            )["n"]
            == 0
        )


@pytest.mark.asyncio
async def test_parent_lock_blocks_every_attribute_action_and_parent_change_fences_stale_selection(
    web_postgres_database: DisposablePostgres,
) -> None:
    context, attributes, runtime = _setup(web_postgres_database)
    selection = _selection(web_postgres_database, "attribute", attributes)
    await runtime.open()
    try:
        await _review(
            runtime,
            context,
            "object",
            "lock",
            _selection(web_postgres_database, "object", context.selected_object_ids),
        )
        assert (await _review(runtime, context, "attribute", "lock", selection))[
            "denial_code"
        ] == "metadata_revision_conflict"
        fresh = _selection(web_postgres_database, "attribute", attributes)
        for action in ("lock", "unlock", "deactivate", "reactivate"):
            assert (await _review(runtime, context, "attribute", action, fresh))[
                "denial_code"
            ] == "object_locked"
        await _review(
            runtime,
            context,
            "object",
            "unlock",
            _selection(web_postgres_database, "object", context.selected_object_ids),
        )
        allowed = await _review(
            runtime,
            context,
            "attribute",
            "lock",
            _selection(web_postgres_database, "attribute", attributes),
        )
        assert allowed["action_count"] == len(attributes)
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["identity", "role", "expired", "owner", "workload"])
async def test_review_and_matching_replay_require_current_human_access_and_owned_lock(
    web_postgres_database: DisposablePostgres,
    failure: str,
) -> None:
    context, _, runtime = _setup(web_postgres_database)
    selection = _selection(web_postgres_database, "object", context.selected_object_ids)
    key = uuid4()
    await runtime.open()
    try:
        assert (await _review(runtime, context, "object", "lock", selection, key=key))[
            "denial_code"
        ] is None
        expected = "authorization_denied"
        if failure == "identity":
            context = replace(context, entra_object_id=uuid4())
        else:
            with web_postgres_database.connect_owner() as connection:
                if failure == "role":
                    connection.execute(
                        "UPDATE security.tenant_principal_access SET tenant_role='viewer' "
                        "WHERE tenant_id=%s",
                        (context.tenant_id,),
                    )
                elif failure == "expired":
                    connection.execute(
                        "UPDATE security.tenant_lock SET "
                        "tenant_lock_acquired_time=clock_timestamp()-interval '2 minutes',"
                        "tenant_lock_expires_time=clock_timestamp()-interval '1 second' "
                        "WHERE tenant_id=%s",
                        (context.tenant_id,),
                    )
                    expected = "tenant_lock_required"
                elif failure == "owner":
                    other = require_row(
                        connection.execute(
                            "INSERT INTO security.principal("
                            "principal_type,principal_display_name,principal_email) "
                            "VALUES('user','Other review actor','review@example.test') "
                            "RETURNING principal_id"
                        ).fetchone()
                    )["principal_id"]
                    connection.execute(
                        "UPDATE security.tenant_lock SET locked_by_principal_id=%s "
                        "WHERE tenant_id=%s",
                        (other, context.tenant_id),
                    )
                    expected = "tenant_locked"
        denied = await _review(
            runtime,
            context,
            "object",
            "lock",
            selection,
            key=key,
            principal_type="service_principal" if failure == "workload" else "user",
        )
        assert denied["denial_code"] == expected
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_sql_rejects_untyped_duplicate_extra_and_oversized_selections(
    web_postgres_database: DisposablePostgres,
) -> None:
    context, _, runtime = _setup(web_postgres_database)
    selected = _selection(web_postgres_database, "object", context.selected_object_ids)[0]
    invalid: list[object] = [
        [],
        {},
        [selected] * 2,
        [selected] * 201,
        [{**selected, "record_id": True}],
        [{**selected, "record_id": "1"}],
        [{**selected, "record_id": 1.5}],
        [{**selected, "record_id": 2**63}],
        [{**selected, "expected_revision": "A" * 64}],
        [{**selected, "extra": "forbidden"}],
        [{**selected, "expected_revision": "x" * 32769}],
        [None],
    ]
    await runtime.open()
    try:
        for records in invalid:
            assert (await _review(runtime, context, "object", "lock", records))[
                "denial_code"
            ] == "invalid_request"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_review_owns_source_tenant_on_shared_placement_and_preserves_existing_metadata_draft(
    web_postgres_database: DisposablePostgres,
) -> None:
    context, _, runtime = _setup(web_postgres_database)
    other = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE core.object SET connection_id=(SELECT connection_id FROM core.object "
            "WHERE object_id=%s) WHERE object_id=ANY(%s)",
            (other.selected_object_ids[0], list(context.selected_object_ids)),
        )
        connection.execute(
            "SELECT * FROM mcp.create_metadata_change_set(%s,%s,'user',%s,%s,%s)",
            (context.entra_tenant_id, context.entra_object_id, context.tenant_id, uuid4(), uuid4()),
        )
        before = connection.execute(
            "SELECT * FROM mcp.metadata_change_set WHERE tenant_id=%s", (context.tenant_id,)
        ).fetchall()
    selection = _selection(web_postgres_database, "object", context.selected_object_ids)
    await runtime.open()
    try:
        assert (await _review(runtime, other, "object", "lock", selection))[
            "denial_code"
        ] == "metadata_selection_conflict"
        assert (await _review(runtime, context, "object", "lock", selection))[
            "action_count"
        ] == len(selection)
    finally:
        await runtime.close()
    with web_postgres_database.connect_owner() as connection:
        assert (
            connection.execute(
                "SELECT * FROM mcp.metadata_change_set WHERE tenant_id=%s", (context.tenant_id,)
            ).fetchall()
            == before
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("same_request", [False, True])
async def test_concurrent_reviews_serialize_without_lock_upgrade_deadlock(
    web_postgres_database: DisposablePostgres,
    same_request: bool,
) -> None:
    context, _, runtime = _setup(web_postgres_database)
    selection = _selection(web_postgres_database, "object", context.selected_object_ids)
    key = uuid4()
    await runtime.open()
    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                _review(runtime, context, "object", "lock", selection, key=key),
                _review(
                    runtime,
                    context,
                    "object",
                    "lock",
                    selection[::-1],
                    key=key if same_request else uuid4(),
                ),
            ),
            timeout=5,
        )
    finally:
        await runtime.close()
    assert sum(row["denial_code"] is None for row in results) == (2 if same_request else 1)
    if same_request:
        assert results[0] == results[1]
    else:
        assert any(row["denial_code"] == "metadata_revision_conflict" for row in results)


@pytest.mark.asyncio
@pytest.mark.parametrize("start_first", [False, True])
async def test_review_serializes_with_actual_workflow_start(
    web_postgres_database: DisposablePostgres,
    start_first: bool,
) -> None:
    context, _, runtime = _setup(web_postgres_database)
    selection = _selection(web_postgres_database, "object", context.selected_object_ids)
    with web_postgres_database.connect_owner() as connection:
        run_id = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(
                    context,
                    correlation_id=uuid4(),
                    workflow="profiling",
                    execution_mode=None,
                ),
            ).fetchone()
        )["workflow_run_id"]
    start_sql = "SELECT * FROM application.start_workflow_run(%s,%s,'user',%s,%s)"
    start_parameters = (
        context.entra_tenant_id,
        context.entra_object_id,
        run_id,
        context.model_revision,
    )
    review_parameters = (
        context.entra_tenant_id,
        context.entra_object_id,
        "user",
        context.tenant_id,
        "object",
        "lock",
        Jsonb(selection),
        uuid4(),
    )
    started = asyncio.Event()

    async def second_operation():
        async with runtime.write_transaction() as transaction:
            started.set()
            return await transaction.fetch_one(
                REVIEW_SQL if start_first else start_sql,
                review_parameters if start_first else start_parameters,
            )

    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            await transaction.fetch_one(
                start_sql if start_first else REVIEW_SQL,
                start_parameters if start_first else review_parameters,
            )
            competing = asyncio.create_task(second_operation())
            await asyncio.wait_for(started.wait(), timeout=2)
            await asyncio.sleep(0.05)
            assert not competing.done()
        result = await asyncio.wait_for(competing, timeout=5)
        assert result is not None
        if start_first:
            assert result["denial_code"] == "tenant_workflow_conflict"
        else:
            assert result["workflow_run_state"] == "running"
    finally:
        await runtime.close()


def test_review_audit_is_private_append_only_and_helpers_never_gain_definer_authority(
    web_postgres_database: DisposablePostgres,
) -> None:
    with web_postgres_database.connect_owner() as connection:
        rows = connection.execute(
            "SELECT role,has_table_privilege(role,'application.metadata_review_event',"
            "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE') AS audit_access,"
            "has_table_privilege(role,'core.object','INSERT,UPDATE,DELETE') AS core_mutation,"
            "has_function_privilege(role,'application.review_metadata_records("
            "uuid,uuid,character varying,bigint,character varying,character varying,jsonb,uuid)',"
            "'EXECUTE') AS review FROM unnest(ARRAY["
            "'gds_app_write','gds_web_write','gds_notebook_runtime']) AS role ORDER BY role"
        ).fetchall()
        assert all(not row["audit_access"] and not row["core_mutation"] for row in rows)
        assert [row["role"] for row in rows if row["review"]] == ["gds_web_write"]
        helpers = connection.execute(
            "SELECT prosecdef,provolatile,proisstrict FROM pg_proc WHERE oid IN ("
            "'application.metadata_object_review_revision(core.object)'::regprocedure,"
            "'application.metadata_attribute_review_revision(core.attribute,core.object)'::regprocedure)"
        ).fetchall()
        assert len(helpers) == 2
        assert all(
            not row["prosecdef"] and row["provolatile"] == "i" and row["proisstrict"]
            for row in helpers
        )
    context = seed_workflow_context(web_postgres_database)
    selection = _selection(web_postgres_database, "object", context.selected_object_ids)
    with web_postgres_database.connect_owner() as connection:
        event = require_row(
            connection.execute(
                REVIEW_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    "user",
                    context.tenant_id,
                    "object",
                    "lock",
                    Jsonb(selection),
                    uuid4(),
                ),
            ).fetchone()
        )["review_event_id"]
    with pytest.raises(RaiseException), web_postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE application.metadata_review_event SET action_count=0 "
            "WHERE metadata_review_event_id=%s",
            (event,),
        )
