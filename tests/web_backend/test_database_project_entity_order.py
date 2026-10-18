"""The web's validated Project draft uses the same dependency-safe materializer."""

from dataclasses import replace
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.project import (
    StageProjectChange,
    load_project_physical_scope,
    validate_project_stage_changes,
)
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.application.project_snapshot import build_project_snapshot
from gds_etl_workbench.domain.errors import (
    InvalidRequestError,
    ProjectChangeSetNotValidatedError,
)
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.project_change_sets.contracts import (
    CreateProjectChangeSetRequest,
    ExpectedDraftRevisionRequest,
    StageProjectChangeSetRequest,
)
from gds_workbench_api.features.project_change_sets.service import (
    DatabaseProjectChangeSetService,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_project_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,  # pyright: ignore[reportPrivateUsage]
    _seed_project_foundation,  # pyright: ignore[reportPrivateUsage]
)
from tests.mcp.test_database_project_entity_order import (
    assert_entity_layers_preserved,
    entity_layer_graph,
)


@pytest.mark.asyncio
async def test_web_validated_draft_applies_both_bound_layers_once(
    web_postgres_database: DisposablePostgres,
) -> None:
    prefix = f"WEB_BINDING_{uuid4().hex}"
    project_id, tenant_id = _seed_project_foundation(
        web_postgres_database, code_prefix=prefix
    )
    _acquire_tenant_lock(web_postgres_database, tenant_id)
    graph = entity_layer_graph(prefix)
    scope_records = graph.pop("project_input_scope")
    # Scope is fixture setup, mirroring the separately governed Scope command.
    # Ordinary web drafts must never acquire direct Scope mutation authority.
    with web_postgres_database.connect_owner() as connection:
        scoped = connection.execute(
            """
            INSERT INTO project.project_input_scope (project_id, object_id)
            SELECT %s, object.object_id
              FROM core.object AS object
             WHERE object.source_tenant_id = %s
               AND object.object_schema = 'src' AND object.object_name = 'orders'
            RETURNING project_input_scope_id
            """,
            (project_id, tenant_id),
        ).fetchall()
        assert len(scoped) == 1
    principal = StaticIdentityProvider().request_principal(None)
    project = ProjectReadContext(
        project_id=project_id,
        tenant_id=tenant_id,
        project_name="Project Tool Round Trip",
        project_revision=1,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    service = DatabaseProjectChangeSetService(
        database=database, authorizer=AuthorizationService()
    )
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            baseline = await build_project_snapshot(transaction, project)
            physical = await load_project_physical_scope(transaction, project)
            canonical = validate_future_graph(
                snapshot=baseline, staged_documents=graph, physical_scope=physical
            )
            assert canonical.valid
        created = await service.create_or_resume(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=CreateProjectChangeSetRequest(expected_project_revision=1),
            idempotency_key=uuid4(),
        )
        with pytest.raises(InvalidRequestError):
            await service.stage(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                change_set_id=created.project_change_set_id,
                command=StageProjectChangeSetRequest(
                    expected_draft_revision=created.draft_revision,
                    changes=[
                        StageProjectChange(
                            dataset="project_input_scope", records=scope_records
                        )
                    ],
                ),
                idempotency_key=uuid4(),
            )
        rejected = await service.get(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            change_set_id=created.project_change_set_id,
            dataset="project_input_scope",
        )
        assert rejected.draft_revision == created.draft_revision
        assert not rejected.records
        staged = await service.stage(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            change_set_id=created.project_change_set_id,
            command=StageProjectChangeSetRequest(
                expected_draft_revision=created.draft_revision,
                changes=[
                    StageProjectChange(dataset=key, records=rows)
                    for key, rows in graph.items()
                ],
            ),
            idempotency_key=uuid4(),
        )
        expected = validate_project_stage_changes(
            [
                StageProjectChange(dataset=key, records=rows)
                for key, rows in graph.items()
            ]
        )
        for dataset in graph:
            draft = await service.get(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                change_set_id=created.project_change_set_id,
                dataset=dataset,
            )
            assert draft.records == expected[dataset], (
                "Every accepted dataset must survive Stage before Validate and Apply."
            )
        command = ExpectedDraftRevisionRequest(
            expected_draft_revision=staged.draft_revision
        )
        validated = await service.validate(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            change_set_id=created.project_change_set_id,
            command=command,
            idempotency_key=uuid4(),
        )
        assert validated.valid
        idempotency_key = uuid4()
        applied = await service.apply(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            change_set_id=created.project_change_set_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        assert applied.project_revision == 2
        assert applied.action_count > 0
        # Ordinary Project Change Set Apply is not the Workflow Run replay API.
        with pytest.raises(ProjectChangeSetNotValidatedError):
            await service.apply(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                change_set_id=created.project_change_set_id,
                command=command,
                idempotency_key=idempotency_key,
            )
        async with database.read_transaction() as transaction:
            snapshot = await build_project_snapshot(
                transaction, replace(project, project_revision=2)
            )
            assert_entity_layers_preserved(snapshot, canonical)
            current_physical = await load_project_physical_scope(transaction, project)
            assert validate_future_graph(
                snapshot=snapshot, staged_documents={}, physical_scope=current_physical
            ).valid
        with web_postgres_database.connect_owner() as connection:
            row = connection.execute(
                "SELECT project_revision FROM project.project WHERE project_id = %s",
                (project_id,),
            ).fetchone()
            assert row == {"project_revision": 2}
            events = connection.execute(
                "SELECT count(*) AS count FROM mcp.project_change_set_event "
                "WHERE project_change_set_id = %s AND event_type = 'applied'",
                (created.project_change_set_id,),
            ).fetchone()
            assert events == {"count": 1}
    finally:
        await database.close()
