"""Input Scope additions use the same governed transaction as reviewed Bindings."""

# pyright: reportPrivateUsage=false
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.model_change_sets.input_scope import (
    AddInputScopeRequest,
)
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
)
from gds_workbench_api.features.models import ModelRevisionConflictError

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _seed_model_foundation,
)


async def test_scope_add_is_locked_fenced_additive_and_idempotent(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    model_id, tenant_id = _seed_model_foundation(fixture, code_prefix=f"SCOPE_{uuid4().hex}")
    with fixture.connect_owner() as connection:
        rows = connection.execute(
            "SELECT object_id, object_schema, object_name FROM core.object "
            "WHERE source_tenant_id=%s",
            (tenant_id,),
        ).fetchall()
    source = next(
        row["object_id"]
        for row in rows
        if row["object_schema"] == "src" and row["object_name"] == "orders"
    )
    customer = next(
        row["object_id"]
        for row in rows
        if row["object_schema"] == "src" and row["object_name"] == "customers"
    )
    silver = next(row["object_id"] for row in rows if row["object_schema"] == "silver")
    principal = StaticIdentityProvider().request_principal(None)
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseModelChangeSetService(database=database, authorizer=AuthorizationService())
    await database.open()
    try:
        command = AddInputScopeRequest(expected_model_revision=1, object_ids=[source])
        with pytest.raises(WorkbenchError):
            await service.add_input_scope(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command,
                idempotency_key=uuid4(),
            )
        _acquire_tenant_lock(fixture, tenant_id)
        key = uuid4()
        result = await service.add_input_scope(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=command,
            idempotency_key=key,
        )
        assert result.action_count == 1 and result.model_revision == 2
        replay = await service.add_input_scope(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=command,
            idempotency_key=key,
        )
        assert replay == result
        with pytest.raises(ModelRevisionConflictError):
            await service.add_input_scope(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command,
                idempotency_key=uuid4(),
            )
        with pytest.raises(InvalidRequestError):
            await service.add_input_scope(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=AddInputScopeRequest(expected_model_revision=2, object_ids=[silver]),
                idempotency_key=uuid4(),
            )
        await service.add_input_scope(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=AddInputScopeRequest(expected_model_revision=2, object_ids=[customer]),
            idempotency_key=uuid4(),
        )
        no_op = await service.add_input_scope(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=AddInputScopeRequest(expected_model_revision=3, object_ids=[source]),
            idempotency_key=uuid4(),
        )
        assert no_op.action_count == 0 and no_op.model_revision == 3
        with pytest.raises(WorkbenchError):
            await service.add_input_scope(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=AddInputScopeRequest(expected_model_revision=3, object_ids=[customer]),
                idempotency_key=key,
            )
        with fixture.connect_owner() as connection:
            scopes = connection.execute(
                "SELECT object_id FROM model.model_input_scope WHERE model_id=%s AND is_active",
                (model_id,),
            ).fetchall()
        assert {row["object_id"] for row in scopes} == {source, customer}
        with fixture.connect_owner() as connection:
            connection.execute(
                "UPDATE model.model_input_scope SET is_active=FALSE, "
                "model_input_scope_is_locked=TRUE WHERE model_id=%s AND object_id=%s",
                (model_id, customer),
            )
        with pytest.raises(InvalidRequestError):
            await service.add_input_scope(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=AddInputScopeRequest(expected_model_revision=3, object_ids=[customer]),
                idempotency_key=uuid4(),
            )
        with fixture.connect_owner() as connection:
            preserved = connection.execute(
                "SELECT is_active, model_input_scope_is_locked FROM model.model_input_scope "
                "WHERE model_id=%s AND object_id=%s",
                (model_id, customer),
            ).fetchone()
        assert preserved == {"is_active": False, "model_input_scope_is_locked": True}
    finally:
        await database.close()
