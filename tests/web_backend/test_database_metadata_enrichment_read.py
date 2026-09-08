"""Exercise enrichment result reads as the actual web runtime and a Tenant viewer."""

# Fixture-only completion setup is shared with the SQL boundary tests.
# pyright: reportPrivateUsage=false

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import TenantNotFoundError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata_enrichment.read_service import (
    DatabaseMetadataEnrichmentReadService,
)
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError

from tests.mcp.conftest import (
    bootstrap_postgres_database as bootstrap_postgres_database,
)
from tests.mcp.test_database_metadata_enrichment_execution import (
    _complete,
    _field,
    _load,
    _start,
)
from tests.mcp.test_database_notebook_workflows import (
    NotebookActor,
)
from tests.mcp.test_database_notebook_workflows import (
    notebook_actor as notebook_actor,
)
from tests.mcp.test_database_workflow_run_lifecycle import seed_workflow_context


async def test_enrichment_results_are_readable_without_lock_and_hide_reowned_labels(
    notebook_actor: NotebookActor,
) -> None:
    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    object_id, attribute_id = attributes[0]
    snapshot = _load(actor, context, run_id)
    completed = _complete(
        actor,
        context,
        run_id,
        claim,
        snapshot["baseline_digest"],
        [
            _field(
                object_id,
                attribute_id,
                "attribute_inferred_data_type",
                "bigint",
                method="registered_type",
            )
        ],
    )
    with actor.database.connect_owner() as connection:
        connection.execute(
            (
                "UPDATE security.tenant_principal_access SET tenant_role = 'viewer' WHERE "
                "tenant_id = %s AND principal_id = %s"
            ),
            (context.tenant_id, context.principal_id),
        )
        connection.execute(
            """UPDATE security.tenant_lock
                  SET tenant_lock_acquired_time = clock_timestamp() - INTERVAL '1 hour',
                      tenant_lock_expires_time = clock_timestamp() - INTERVAL '1 second'
                WHERE tenant_id = %s""",
            (context.tenant_id,),
        )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    runtime = WebPostgresDatabase(
        dsn=actor.database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await runtime.open()
    try:
        service = DatabaseMetadataEnrichmentReadService(
            database=runtime, authorizer=AuthorizationService()
        )
        first = await service.read_results(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=run_id,
            limit=1,
        )
        assert len(first.results) == 1
        assert first.result_count == completed["result_count"]
        assert first.counts == completed["counts"]
        assert first.applied_field_counts == {
            "object_description": 0,
            "attribute_description": 0,
            "attribute_inferred_data_type": 1,
        }
        assert first.next_offset == 1
        page = await service.read_results(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=run_id,
        )
        applied = next(row for row in page.results if row.status == "applied")
        assert applied.object_name is not None
        assert applied.attribute_name is not None
        assert applied.storage_type == "string"
        assert applied.applied_value == "bigint"
        with pytest.raises(WorkflowRunNotFoundError):
            await service.read_results(
                principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id + 1_000_000,
                workflow_run_id=run_id,
            )
        foreign = seed_workflow_context(actor.database)
        with pytest.raises(TenantNotFoundError):
            await service.read_results(
                principal,
                tenant_id=foreign.tenant_id,
                model_id=context.model_id,
                workflow_run_id=run_id,
            )
        with actor.database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.object SET source_tenant_id = %s WHERE object_id = %s",
                (foreign.tenant_id, object_id),
            )
        reowned = await service.read_results(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=run_id,
        )
        historical = next(row for row in reowned.results if row.result_id == applied.result_id)
        assert historical.applied_value == "bigint"
        assert (
            historical.object_schema,
            historical.object_name,
            historical.attribute_name,
            historical.storage_type,
        ) == (None, None, None, None)
    finally:
        await runtime.close()
