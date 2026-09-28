"""Typed Mapping outcome projections against disposable PostgreSQL only."""

# Fixture builders deliberately share synthetic seed helpers.
# pyright: reportPrivateUsage=false
from typing import Literal

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import TenantNotFoundError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.models import DatabaseModelService
from gds_workbench_api.features.workflows.overview import DatabaseWorkflowOverviewService
from gds_workbench_api.features.workflows.runs import DatabaseWorkflowRunService
from gds_workbench_api.features.workflows.runs.contracts import MappingRunOutcome
from gds_workbench_api.features.workflows.runs.service import read_mapping_run_outcomes

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.web_backend.test_database_mapping_source_context import _seed_mapping_scope


@pytest.mark.parametrize("scenario", ["legacy", "mixed", "recovered", "all_failed"])
async def test_mapping_outcomes_use_frozen_ordinals_and_bounded_tenant_scoped_reads(
    web_postgres_database: DisposablePostgres,
    scenario: Literal["legacy", "mixed", "recovered", "all_failed"],
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=False)
    model_id, run_id = scope.plan.model_id, scope.plan.workflow_run_id
    pair_count = {"legacy": 1, "mixed": 4, "recovered": 4, "all_failed": 205}[scenario]
    with web_postgres_database.connect_owner() as connection:
        actor = require_row(connection.execute(
            "SELECT entra_tenant_id, entra_object_id FROM security.entra_principal_identity "
            "WHERE principal_id=%s", (scope.plan.actor_principal_id,),
        ).fetchone())
        system = require_row(connection.execute(
            "SELECT system_code FROM core.system WHERE system_id=%s", (scope.source_system_id,),
        ).fetchone())
        # Frozen history deliberately need not resolve to live Entity rows.
        # Sparse selection_order values must still map to one-based event ordinals.
        connection.execute(
            """
            WITH entities AS (
                INSERT INTO application.workflow_run_entity_selection (
                    workflow_run_id, model_id, modeled_entity_type, modeled_entity_id,
                    modeled_entity_schema_name, modeled_entity_name, selection_order
                ) SELECT %s, %s, 'logical_entity', 1000000 + ordinal,
                         'historical_schema', 'HistoricalEntity' || ordinal, ordinal * 10
                    FROM generate_series(2, %s) AS ordinal
                RETURNING workflow_run_entity_selection_id, selection_order
            )
            INSERT INTO application.workflow_run_mapping_target_selection (
                workflow_run_id, model_id, workflow_run_entity_selection_id,
                source_system_id, selection_order
            ) SELECT %s, %s, workflow_run_entity_selection_id, %s, selection_order FROM entities
            """,
            (run_id, model_id, pair_count, run_id, model_id, scope.source_system_id),
        )
        events: list[tuple[str, int, int, str]]
        if scenario in {"mixed", "recovered"}:
            events = [
                ("mapping.pair_failed", 1, 4, "An earlier outcome must not override the latest."),
                ("mapping.pair_completed", 1, 4, "Completed."),
                ("mapping.pair_preserved", 2, 4, "Preserved."),
                ("mapping.pair_no_source", 3, 4, "No applicable source."),
                ("mapping.pair_failed", 4, 4, "First bounded diagnostic."),
                ("mapping.pair_failed", 4, 4, "Required join evidence is unavailable."),
                ("mapping.mapping_authoring", 2, 4, "Failed: legacy prose is not an outcome."),
                ("mapping.pair_failed", 3, 5, "Wrong frozen total is ignored."),
                ("mapping.pair_completed", 0, 4, "Zero is not a frozen ordinal."),
            ]
            if scenario == "recovered":
                events.append(("mapping.pair_completed", 4, 4, "Completed on retry."))
        elif scenario == "legacy":
            events = [("mapping.mapping_authoring", 1, 1, "Failed: legacy prose only.")]
        else:
            events = [
                ("mapping.pair_failed", ordinal, pair_count, "Required evidence is unavailable.")
                for ordinal in range(1, pair_count + 1)
            ]
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO model.model_event_log (
                    model_id, correlation_id, workflow_run_id, model_event_log_sequence,
                    model_event_log_attempt, model_workflow, model_event_log_stage,
                    model_event_log_status, model_event_log_message,
                    model_event_log_current, model_event_log_total
                ) VALUES (%s, %s, %s, %s, 1, 'mapping', %s, 'warning', %s, %s, %s)
                """,
                [
                    (model_id, scope.plan.correlation_id, run_id, sequence, stage,
                     message, current, total)
                    for sequence, (stage, current, total, message) in enumerate(events, start=1)
                ],
            )
        acquired = require_row(connection.execute(
            "SELECT acquired FROM security.acquire_tenant_lock(%s,%s,'user',%s,60,%s)",
            (actor["entra_tenant_id"], actor["entra_object_id"], scope.tenant_id,
             "Disposable read projection verification"),
        ).fetchone())
        assert acquired["acquired"]
        if scenario == "all_failed":
            connection.execute(
                "SELECT * FROM application.fail_workflow_run(%s,%s,'user',%s,1,%s,%s)",
                (actor["entra_tenant_id"], actor["entra_object_id"], run_id,
                 "mapping_evidence_unresolved", "Required evidence is unavailable."),
            )
        else:
            connection.execute(
                "SELECT * FROM application.complete_workflow_run(%s,%s,'user',%s,1,0)",
                (actor["entra_tenant_id"], actor["entra_object_id"], run_id),
            )

    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=actor["entra_tenant_id"],
        entra_object_id=actor["entra_object_id"],
    )
    runtime = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(), pool_min=1, pool_max=1,
        pool_timeout_seconds=5,
    )
    service = DatabaseWorkflowRunService(
        database=runtime, authorizer=AuthorizationService(),
        cursor_signing_key=b"disposable-mapping-read-test-key-32-bytes",
    )
    await runtime.open()
    try:
        detail = await service.read_run(
            principal, tenant_id=scope.tenant_id, model_id=model_id, workflow_run_id=run_id,
        )
        ledger = await service.list_runs(
            principal, tenant_id=scope.tenant_id, model_id=model_id, workflow="mapping",
            run_state=None, page_size=25, cursor=None,
        )
        assert ledger.items[0].mapping_outcome == detail.mapping_outcome
        models = await DatabaseModelService(
            database=runtime, authorizer=AuthorizationService(),
            cursor_signing_key=b"disposable-model-read-test-key-32-bytes",
        ).list_models(
            principal, tenant_id=scope.tenant_id, model_status="active", page_size=25, cursor=None,
        )
        assert models.items[0].latest_run_status == {
            "legacy": "completed", "mixed": "partial_results",
            "recovered": "completed", "all_failed": "failed",
        }[scenario]
        if scenario == "legacy":
            assert detail.mapping_outcome is None
            assert detail.mapping_failures == ()
            assert not detail.mapping_failures_truncated
        elif scenario == "recovered":
            assert detail.mapping_outcome == MappingRunOutcome(
                completed_pair_count=2, preserved_pair_count=1,
                no_source_pair_count=1, failed_pair_count=0,
            )
            assert not detail.mapping_failures
            assert not detail.mapping_failures_truncated
        elif scenario == "mixed":
            assert detail.mapping_outcome == MappingRunOutcome(
                completed_pair_count=1, preserved_pair_count=1,
                no_source_pair_count=1, failed_pair_count=1,
            )
            assert len(detail.mapping_failures) == 1
            assert detail.mapping_failures[0].model_dump() == {
                "source_system_id": scope.source_system_id,
                "system_code": system["system_code"],
                "modeled_entity_id": 1000004,
                "entity_schema_name": "historical_schema",
                "entity_name": "HistoricalEntity4",
                "message": "Required join evidence is unavailable.",
            }
            assert not detail.mapping_failures_truncated
        else:
            assert detail.workflow_run_state == "failed"
            assert detail.mapping_outcome == MappingRunOutcome(
                completed_pair_count=0, preserved_pair_count=0,
                no_source_pair_count=0, failed_pair_count=205,
            )
            assert len(detail.mapping_failures) == 200
            assert detail.mapping_failures[-1].entity_name == "HistoricalEntity200"
            assert detail.mapping_failures_truncated

        overview = await DatabaseWorkflowOverviewService(
            database=runtime, authorizer=AuthorizationService(),
        ).read_overview(principal, tenant_id=scope.tenant_id, model_id=model_id)
        mapping_section = next(item for item in overview.section_states if item.section == "mapping")
        assert mapping_section.state == {
            "legacy": "completed", "mixed": "results_available",
            "recovered": "completed", "all_failed": "failed",
        }[scenario]

        # The query itself fences Tenant and Model, even independently of the
        # public read service's authorization check.
        async with runtime.read_transaction() as transaction:
            assert await read_mapping_run_outcomes(
                transaction, tenant_id=scope.placement_tenant_id,
                model_id=model_id, workflow_run_ids=(run_id,),
            ) == {}
            assert await read_mapping_run_outcomes(
                transaction, tenant_id=scope.tenant_id,
                model_id=model_id + 100000, workflow_run_ids=(run_id,),
            ) == {}
        with pytest.raises(TenantNotFoundError):
            await service.read_run(
                principal, tenant_id=scope.placement_tenant_id,
                model_id=model_id, workflow_run_id=run_id,
            )
    finally:
        await runtime.close()
