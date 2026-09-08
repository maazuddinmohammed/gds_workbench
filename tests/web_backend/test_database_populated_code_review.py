"""Populated Code review must project internal generation context to its public shape."""

# pyright: reportPrivateUsage=false
from uuid import uuid4

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.code_generation import (
    CodeGenerationTargetFilters,
    DatabaseCodeGenerationService,
)
from gds_workbench_api.features.model_change_sets.contracts import (
    CreateModelChangeSetRequest,
    ExpectedDraftRevisionRequest,
    StageModelChangeSetRequest,
)
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import complete_model_graph
from tests.mcp.test_database_model_binding_order import bound_layer_graph
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _replace_codes,
    _seed_model_foundation,
)


async def test_populated_code_target_and_artifact_reads_keep_public_target_shape(
    web_postgres_database: DisposablePostgres,
) -> None:
    prefix = f"CODE_REVIEW_{uuid4().hex}"
    model_id, tenant_id = _seed_model_foundation(
        web_postgres_database, code_prefix=prefix
    )
    _acquire_tenant_lock(web_postgres_database, tenant_id)
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            "INSERT INTO model.model_input_scope(model_id,object_id) "
            "SELECT %s,object_id FROM core.object WHERE source_tenant_id=%s "
            "AND object_schema IN ('src','bronze')",
            (model_id, tenant_id),
        )
    graph = bound_layer_graph(prefix)
    complete = _replace_codes(complete_model_graph(), code_prefix=prefix)
    for dataset in ("generated_code", "generated_code_source_system"):
        graph[dataset] = complete[dataset]
    graph.pop("model_input_scope")
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    principal = StaticIdentityProvider().request_principal(None)
    authorizer = AuthorizationService()
    drafts = DatabaseModelChangeSetService(database=database, authorizer=authorizer)
    code = DatabaseCodeGenerationService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=b"populated-code-review-fixture-key",
    )
    await database.open()
    try:
        created = await drafts.create_or_resume(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=CreateModelChangeSetRequest(expected_model_revision=1),
            idempotency_key=uuid4(),
        )
        staged = await drafts.stage(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            command=StageModelChangeSetRequest(
                expected_draft_revision=created.draft_revision,
                changes=[
                    StageModelChange(dataset=key, records=rows)
                    for key, rows in graph.items()
                ],
            ),
            idempotency_key=uuid4(),
        )
        command = ExpectedDraftRevisionRequest(
            expected_draft_revision=staged.draft_revision
        )
        validated = await drafts.validate(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            command=command,
            idempotency_key=uuid4(),
        )
        assert validated.valid
        await drafts.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            command=command,
            idempotency_key=uuid4(),
        )
        page = await code.list_targets(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=CodeGenerationTargetFilters(),
            page_size=50,
            cursor=None,
        )
        assert len(page.items) == 1
        target = page.items[0]
        assert target.target.object_name == "Order"
        assert target.target.source_tenant_id == tenant_id
        assert target.target.tenant_id != tenant_id
        assert target.mapping_support_count == 1
        assert target.artifact_count == 1
        artifact = await code.read_artifact(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            generated_sql_artifact_id=target.artifacts[0].generated_sql_artifact_id,
        )
        assert artifact.target == target.target
        assert artifact.generated_sql == "SELECT * FROM main.silver.Order"
        assert artifact.artifact_is_current
    finally:
        await database.close()
