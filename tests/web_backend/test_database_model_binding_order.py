"""The web's validated Model draft uses the same dependency-safe materializer."""

from dataclasses import replace
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import (
    StageModelChange,
    load_model_physical_scope,
    validate_model_stage_changes,
)
from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.errors import InvalidRequestError, ModelChangeSetNotValidatedError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.model_change_sets.contracts import (
    CreateModelChangeSetRequest,
    ExpectedDraftRevisionRequest,
    StageModelChangeSetRequest,
)
from gds_workbench_api.features.model_change_sets.service import DatabaseModelChangeSetService

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_model_binding_order import (
    assert_bound_layers_preserved,
    bound_layer_graph,
)
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,  # pyright: ignore[reportPrivateUsage]
    _seed_model_foundation,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.asyncio
async def test_web_validated_draft_applies_both_bound_layers_once(
    web_postgres_database: DisposablePostgres,
) -> None:
    prefix = f"WEB_BINDING_{uuid4().hex}"
    model_id, tenant_id = _seed_model_foundation(web_postgres_database, code_prefix=prefix)
    _acquire_tenant_lock(web_postgres_database, tenant_id)
    graph = bound_layer_graph(prefix)
    scope_records = graph.pop("model_input_scope")
    # Scope is fixture setup, mirroring the separately governed Scope command.
    # Ordinary web drafts must never acquire direct Scope mutation authority.
    with web_postgres_database.connect_owner() as connection:
        scoped = connection.execute(
            """
            INSERT INTO model.model_input_scope (model_id, object_id)
            SELECT %s, object.object_id
              FROM core.object AS object
             WHERE object.source_tenant_id = %s
               AND object.object_schema = 'src' AND object.object_name = 'orders'
            RETURNING model_input_scope_id
            """,
            (model_id, tenant_id),
        ).fetchall()
        assert len(scoped) == 1
    principal = StaticIdentityProvider().request_principal(None)
    model = ModelReadContext(
        model_id=model_id,
        tenant_id=tenant_id,
        model_name="Model Tool Round Trip",
        model_revision=1,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    service = DatabaseModelChangeSetService(database=database, authorizer=AuthorizationService())
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            baseline = await build_model_snapshot(transaction, model)
            physical = await load_model_physical_scope(transaction, model)
            canonical = validate_future_graph(
                snapshot=baseline, staged_documents=graph, physical_scope=physical
            )
            assert canonical.valid
        created = await service.create_or_resume(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=CreateModelChangeSetRequest(expected_model_revision=1),
            idempotency_key=uuid4(),
        )
        with pytest.raises(InvalidRequestError):
            await service.stage(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                change_set_id=created.model_change_set_id,
                command=StageModelChangeSetRequest(
                    expected_draft_revision=created.draft_revision,
                    changes=[StageModelChange(dataset="model_input_scope", records=scope_records)],
                ),
                idempotency_key=uuid4(),
            )
        rejected = await service.get(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            dataset="model_input_scope",
        )
        assert rejected.draft_revision == created.draft_revision
        assert not rejected.records
        staged = await service.stage(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            command=StageModelChangeSetRequest(
                expected_draft_revision=created.draft_revision,
                changes=[
                    StageModelChange(dataset=key, records=rows) for key, rows in graph.items()
                ],
            ),
            idempotency_key=uuid4(),
        )
        expected = validate_model_stage_changes(
            [StageModelChange(dataset=key, records=rows) for key, rows in graph.items()]
        )
        for dataset in graph:
            draft = await service.get(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                change_set_id=created.model_change_set_id,
                dataset=dataset,
            )
            assert draft.records == expected[dataset], (
                "Every accepted dataset must survive Stage before Validate and Apply."
            )
        command = ExpectedDraftRevisionRequest(expected_draft_revision=staged.draft_revision)
        validated = await service.validate(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            command=command,
            idempotency_key=uuid4(),
        )
        assert validated.valid
        idempotency_key = uuid4()
        applied = await service.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        assert applied.model_revision == 2
        assert applied.action_count > 0
        # Ordinary Model Change Set Apply is not the Workflow Run replay API.
        with pytest.raises(ModelChangeSetNotValidatedError):
            await service.apply(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                change_set_id=created.model_change_set_id,
                command=command,
                idempotency_key=idempotency_key,
            )
        async with database.read_transaction() as transaction:
            snapshot = await build_model_snapshot(transaction, replace(model, model_revision=2))
            assert_bound_layers_preserved(snapshot, canonical)
            current_physical = await load_model_physical_scope(transaction, model)
            assert validate_future_graph(
                snapshot=snapshot, staged_documents={}, physical_scope=current_physical
            ).valid
        with web_postgres_database.connect_owner() as connection:
            row = connection.execute(
                "SELECT model_revision FROM model.model WHERE model_id = %s", (model_id,)
            ).fetchone()
            assert row == {"model_revision": 2}
            events = connection.execute(
                "SELECT count(*) AS count FROM mcp.model_change_set_event "
                "WHERE model_change_set_id = %s AND event_type = 'applied'",
                (created.model_change_set_id,),
            ).fetchone()
            assert events == {"count": 1}
    finally:
        await database.close()
