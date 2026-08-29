from __future__ import annotations

from collections.abc import Iterator

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    ToolPolicy,
)
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.analysis.validation_service import (
    DatabaseAnalysisValidationRepository,
)
from gds_workbench_api.features.profiling.workflow import (
    DatabaseProfilingWorkflowRepository,
)

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.mcp.test_database_analysis_validation import (
    _seed_analysis_validation,  # pyright: ignore[reportPrivateUsage]
)
from tests.mcp.test_database_profiling_execution_context import (
    _seed_profiling_execution,  # pyright: ignore[reportPrivateUsage]
)


@pytest.fixture(scope="module")
def runtime_postgres() -> Iterator[DisposablePostgres]:
    yield from disposable_postgres()


@pytest.mark.asyncio
async def test_notebook_runtime_loads_the_locked_profiling_context(
    runtime_postgres: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(runtime_postgres)
    database = WebPostgresDatabase(
        dsn=runtime_postgres.notebook_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await database.open()
    try:
        repository = DatabaseProfilingWorkflowRepository(
            database=database,
            environment_code=seed.environment_code,
        )
        context = await repository.load_context(
            RequestPrincipal(
                actor_kind=ActorKind.HUMAN,
                entra_tenant_id=seed.context.entra_tenant_id,
                entra_object_id=seed.context.entra_object_id,
            ),
            tenant_id=seed.context.tenant_id,
            model_id=seed.context.model_id,
            workflow_run_id=seed.workflow_run_id,
            expected_model_revision=seed.context.model_revision,
        )
    finally:
        await database.close()

    assert context.workflow_run_id == seed.workflow_run_id
    assert tuple(target.object.object_id for target in context.targets) == (
        seed.context.selected_object_ids
    )


@pytest.mark.asyncio
async def test_notebook_runtime_loads_the_locked_analysis_validation_context(
    runtime_postgres: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(runtime_postgres)
    database = WebPostgresDatabase(
        dsn=runtime_postgres.notebook_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await database.open()
    try:
        repository = DatabaseAnalysisValidationRepository(
            database=database,
            environment_code=seed.execution.environment_code,
        )
        context = await repository.load_context(
            RequestPrincipal(
                actor_kind=ActorKind.HUMAN,
                entra_tenant_id=seed.execution.context.entra_tenant_id,
                entra_object_id=seed.execution.context.entra_object_id,
            ),
            tenant_id=seed.execution.context.tenant_id,
            model_id=seed.execution.context.model_id,
            workflow_run_id=seed.execution.workflow_run_id,
            expected_model_revision=seed.execution.context.model_revision,
        )
    finally:
        await database.close()

    assert tuple(target.relationship.analysis_result_id for target in context.targets) == (
        seed.active_result_id,
        seed.locked_result_id,
    )


@pytest.mark.asyncio
async def test_notebook_runtime_allows_locking_write_authorization(
    runtime_postgres: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(runtime_postgres)
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=seed.context.entra_tenant_id,
        entra_object_id=seed.context.entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=runtime_postgres.notebook_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await database.open()
    try:
        async with database.write_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            authorization = await AuthorizationService().authorize_tenant(
                transaction,
                principal,
                tenant_id=seed.context.tenant_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
    finally:
        await database.close()

    assert authorization.principal.principal_id is not None
