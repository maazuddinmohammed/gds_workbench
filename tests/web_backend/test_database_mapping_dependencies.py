"""Manual dependency edits preserve the governed write boundary."""

# pyright: reportPrivateUsage=false
from uuid import UUID, uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.mapping.dependencies import SaveMappingDependencyRequest
from gds_workbench_api.features.model_change_sets.contracts import (
    ReviewModelRecordsRequest,
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


async def test_manual_order_is_authorized_fenced_idempotent_and_lock_protected(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    prefix = f"DEP_{uuid4().hex}"
    model_id, tenant_id = _seed_model_foundation(fixture, code_prefix=prefix)
    principal = StaticIdentityProvider().request_principal(None)
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseModelChangeSetService(
        database=database, authorizer=AuthorizationService()
    )
    command = SaveMappingDependencyRequest(
        expected_model_revision=1,
        entity_type="logical_entity",
        source_system_code=f"{prefix}_ERP",
        dependency_order=2,
    )

    async def save(value: SaveMappingDependencyRequest, key: UUID | None = None):
        return await service.save_mapping_dependency(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=value,
            idempotency_key=key or uuid4(),
        )

    await database.open()
    try:
        with pytest.raises(WorkbenchError):
            await save(command)
        _acquire_tenant_lock(fixture, tenant_id)
        key = uuid4()
        result = await save(command, key)
        assert result.model_revision == 2 and result.action_count == 1
        assert await save(command, key) == result
        with pytest.raises(ModelRevisionConflictError):
            await save(command)
        updated = command.model_copy(
            update={"expected_model_revision": 2, "dependency_order": 3}
        )
        assert (await save(updated)).model_revision == 3
        with fixture.connect_owner() as connection:
            row = connection.execute(
                "SELECT mapping_source_system_dependency_id AS id, "
                "source_system_dependency_order AS ordering "
                "FROM workflow.mapping_source_system_dependency WHERE model_id=%s",
                (model_id,),
            ).fetchone()
        assert row is not None and row["ordering"] == 3
        locked = await service.review_records(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=ReviewModelRecordsRequest(
                dataset="mapping_dependency",
                record_ids=[row["id"]],
                action="lock",
                expected_model_revision=3,
            ),
            idempotency_key=uuid4(),
        )
        with pytest.raises(InvalidRequestError):
            await save(
                updated.model_copy(
                    update={"expected_model_revision": locked.model_revision}
                )
            )
        unlocked = await service.review_records(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=ReviewModelRecordsRequest(
                dataset="mapping_dependency",
                record_ids=[row["id"]],
                action="unlock",
                expected_model_revision=locked.model_revision,
            ),
            idempotency_key=uuid4(),
        )
        with pytest.raises(InvalidRequestError):
            await save(
                command.model_copy(
                    update={
                        "expected_model_revision": unlocked.model_revision,
                        "source_system_code": "MISSING_SYSTEM",
                    }
                )
            )
    finally:
        await database.close()
