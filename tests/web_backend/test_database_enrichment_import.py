"""Governed metadata-description imports use fixture-created disposable PostgreSQL."""

# pyright: reportPrivateUsage=false

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata_enrichment.review import (
    DatabaseEnrichmentReviewService,
    ReviewEnrichmentRequest,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_profiling_persistence import _create_run, _seed_attributes
from tests.mcp.test_database_workflow_run_lifecycle import (
    WorkflowContext,
    seed_workflow_context,
)

type RecordType = Literal["object", "attribute"]


@dataclass(frozen=True)
class ImportContext:
    fixture: DisposablePostgres
    project: WorkflowContext
    pairs: tuple[tuple[int, int], ...]
    service: DatabaseEnrichmentReviewService
    principal: RequestPrincipal

    def command(
        self,
        record_type: RecordType,
        action: Literal["import", "reimport", "lock"] = "import",
        *,
        first_only: bool = False,
    ) -> ReviewEnrichmentRequest:
        with self.fixture.connect_owner() as connection:
            records = [
                {
                    "record_id": object_id if record_type == "object" else attribute_id,
                    "expected_revision": require_row(
                        connection.execute(
                            "SELECT workflow.enrichment_review_revision(%s,%s,%s) AS revision",
                            (
                                self.project.project_id,
                                object_id,
                                attribute_id if record_type == "attribute" else None,
                            ),
                        ).fetchone()
                    )["revision"],
                }
                for object_id, attribute_id in (self.pairs[:1] if first_only else self.pairs)
            ]
        return ReviewEnrichmentRequest.model_validate(
            {
                "expected_project_revision": self.project.project_revision,
                "record_type": record_type,
                "action": action,
                "records": records,
            }
        )


@pytest.fixture
async def import_context(
    web_postgres_database: DisposablePostgres,
) -> AsyncIterator[ImportContext]:
    fixture = web_postgres_database
    context = seed_workflow_context(fixture)
    pairs = _seed_attributes(fixture, context)
    with fixture.connect_owner() as connection:
        for index, (object_id, attribute_id) in enumerate(pairs):
            description = "  Registered description  " if index == 0 else " \t\r\n "
            connection.execute(
                "UPDATE core.object SET object_description=%s WHERE object_id=%s",
                (description, object_id),
            )
            connection.execute(
                "UPDATE core.attribute SET attribute_description=%s WHERE attribute_id=%s",
                (description, attribute_id),
            )
        connection.execute(
            "INSERT INTO workflow.attribute_enrichment "
            "(project_id,object_id,attribute_id,attribute_inferred_data_type,"
            "is_natural_key,is_primary_key,is_nullable,is_pii) "
            "VALUES(%s,%s,%s,'BIGINT',TRUE,FALSE,FALSE,NULL)",
            (context.project_id, *pairs[0]),
        )
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=2, pool_timeout_seconds=5
    )
    await database.open()
    try:
        yield ImportContext(
            fixture=fixture,
            project=context,
            pairs=pairs,
            service=DatabaseEnrichmentReviewService(database=database),
            principal=RequestPrincipal(
                actor_kind=ActorKind.HUMAN,
                entra_tenant_id=context.entra_tenant_id,
                entra_object_id=context.entra_object_id,
            ),
        )
    finally:
        await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", ["object", "attribute"])
async def test_import_skip_replace_replay_and_project_isolation(
    import_context: ImportContext, record_type: RecordType
) -> None:
    ctx = import_context
    project = ctx.project
    object_id, attribute_id = ctx.pairs[0]
    with ctx.fixture.connect_owner() as connection:
        before = connection.execute(
            "SELECT to_jsonb(o) AS object, to_jsonb(a) AS attribute "
            "FROM core.object o JOIN core.attribute a USING(object_id) "
            "WHERE o.object_id=ANY(%s) ORDER BY o.object_id, a.attribute_id",
            (list(project.selected_object_ids),),
        ).fetchall()
        other_project_id = require_row(
            connection.execute(
                "INSERT INTO project.project(tenant_id,project_name) "
                "VALUES(%s,%s) RETURNING project_id",
                (project.tenant_id, f"Import isolation {uuid4().hex}"),
            ).fetchone()
        )["project_id"]
        connection.execute(
            "INSERT INTO project.project_input_scope(project_id,object_id) VALUES(%s,%s)",
            (other_project_id, object_id),
        )
    command = ctx.command(record_type)
    key = uuid4()
    first = await ctx.service.review_records(
        ctx.principal,
        tenant_id=project.tenant_id,
        project_id=project.project_id,
        command=command,
        idempotency_key=key,
    )
    assert first.action_count == 1
    assert len(first.records) == len(ctx.pairs)
    assert all(row.is_locked is False for row in first.records)
    assert first == await ctx.service.review_records(
        ctx.principal,
        tenant_id=project.tenant_id,
        project_id=project.project_id,
        command=command,
        idempotency_key=key,
    )
    with pytest.raises(WorkbenchError) as changed_request:
        await ctx.service.review_records(
            ctx.principal,
            tenant_id=project.tenant_id,
            project_id=project.project_id,
            command=command.model_copy(update={"action": "reimport"}),
            idempotency_key=key,
        )
    assert changed_request.value.code == "metadata_revision_conflict"
    with ctx.fixture.connect_owner() as connection:
        assert connection.execute(
            "SELECT to_jsonb(o) AS object, to_jsonb(a) AS attribute "
            "FROM core.object o JOIN core.attribute a USING(object_id) "
            "WHERE o.object_id=ANY(%s) ORDER BY o.object_id, a.attribute_id",
            (list(project.selected_object_ids),),
        ).fetchall() == before
        assert require_row(
            connection.execute(
                "SELECT count(*) AS count FROM application.workflow_run WHERE project_id=%s",
                (project.project_id,),
            ).fetchone()
        )["count"] == 0
        assert require_row(
            connection.execute(
                "SELECT count(*) AS count FROM workflow.object_enrichment WHERE project_id=%s",
                (other_project_id,),
            ).fetchone()
        )["count"] == 0
        assert require_row(
            connection.execute(
                "SELECT count(*) AS count FROM workflow.attribute_enrichment WHERE project_id=%s",
                (other_project_id,),
            ).fetchone()
        )["count"] == 0
        receipt = require_row(
            connection.execute(
                "SELECT action, before_records, records FROM application.metadata_review_event "
                "WHERE metadata_review_event_id=%s",
                (first.review_event_id,),
            ).fetchone()
        )
        assert receipt["action"] == "import"
        assert "Registered description" not in str(receipt)
        assert len(receipt["before_records"]) == len(receipt["records"])

    source_update = (
        "UPDATE core.object SET object_description=%s WHERE object_id=%s"
        if record_type == "object"
        else "UPDATE core.attribute SET attribute_description=%s WHERE attribute_id=%s"
    )
    source_id = object_id if record_type == "object" else attribute_id
    with ctx.fixture.connect_owner() as connection:
        connection.execute(source_update, ("Updated registered description", source_id))
    actions: tuple[tuple[Literal["import", "reimport"], int], ...] = (
        ("import", 0),
        ("reimport", 1),
        ("reimport", 0),
    )
    for action, expected_count in actions:
        current = ctx.command(record_type, action)
        result = await ctx.service.review_records(
            ctx.principal,
            tenant_id=project.tenant_id,
            project_id=project.project_id,
            command=current,
            idempotency_key=uuid4(),
        )
        assert result.action_count == expected_count
        if expected_count == 0:
            assert [row.review_revision for row in result.records] == [
                row.expected_revision for row in current.records
            ]
    with ctx.fixture.connect_owner() as connection:
        connection.execute(source_update, (None, source_id))
    result = await ctx.service.review_records(
        ctx.principal,
        tenant_id=project.tenant_id,
        project_id=project.project_id,
        command=ctx.command(record_type, "reimport"),
        idempotency_key=uuid4(),
    )
    assert result.action_count == 0
    with ctx.fixture.connect_owner() as connection:
        saved = require_row(
            connection.execute(
                "SELECT object_description AS description FROM workflow.object_enrichment "
                "WHERE project_id=%s AND object_id=%s"
                if record_type == "object"
                else "SELECT attribute_description AS description "
                "FROM workflow.attribute_enrichment WHERE project_id=%s AND attribute_id=%s",
                (project.project_id, source_id),
            ).fetchone()
        )
        assert saved["description"] == "Updated registered description"
        attribute = require_row(
            connection.execute(
                "SELECT attribute_inferred_data_type,is_natural_key,is_primary_key,"
                "is_nullable,is_pii FROM workflow.attribute_enrichment "
                "WHERE project_id=%s AND attribute_id=%s",
                (project.project_id, attribute_id),
            ).fetchone()
        )
        assert tuple(attribute.values()) == ("BIGINT", True, False, False, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", ["object", "attribute"])
@pytest.mark.parametrize(
    "guard",
    [
        "source_revision",
        "project_revision",
        "outside_scope",
        "record_lock",
        "blank_record_lock",
        "tenant_lock",
    ],
)
async def test_import_preserves_selection_revision_and_lock_guards(
    import_context: ImportContext, record_type: RecordType, guard: str
) -> None:
    ctx = import_context
    project = ctx.project
    command = ctx.command(record_type, first_only=guard != "blank_record_lock")
    if guard == "outside_scope":
        other_project = seed_workflow_context(ctx.fixture)
        other_object, other_attribute = _seed_attributes(ctx.fixture, other_project)[0]
        command = command.model_copy(
            update={
                "records": [
                    command.records[0].model_copy(
                        update={
                            "record_id": (
                                other_object if record_type == "object" else other_attribute
                            )
                        }
                    )
                ]
            }
        )
    with ctx.fixture.connect_owner() as connection:
        if guard == "source_revision":
            connection.execute(
                "UPDATE core.object SET object_description='Changed' WHERE object_id=%s",
                (ctx.pairs[0][0],),
            )
        elif guard == "project_revision":
            command = command.model_copy(
                update={"expected_project_revision": project.project_revision + 1}
            )
        elif guard == "record_lock":
            connection.execute(
                "INSERT INTO workflow.object_enrichment(project_id,object_id,is_locked) "
                "VALUES(%s,%s,TRUE)",
                (project.project_id, ctx.pairs[0][0]),
            )
        elif guard == "blank_record_lock":
            if record_type == "object":
                connection.execute(
                    "INSERT INTO workflow.object_enrichment(project_id,object_id,is_locked) "
                    "VALUES(%s,%s,TRUE)",
                    (project.project_id, ctx.pairs[-1][0]),
                )
            else:
                connection.execute(
                    "INSERT INTO workflow.attribute_enrichment "
                    "(project_id,object_id,attribute_id,is_locked) VALUES(%s,%s,%s,TRUE)",
                    (project.project_id, *ctx.pairs[-1]),
                )
        elif guard == "tenant_lock":
            connection.execute(
                "SELECT security.release_tenant_lock(%s,%s,'user',%s)",
                (project.entra_tenant_id, project.entra_object_id, project.tenant_id),
            )
    if guard in ("record_lock", "blank_record_lock"):
        command = ctx.command(record_type, first_only=guard != "blank_record_lock")
    with pytest.raises(WorkbenchError) as failure:
        await ctx.service.review_records(
            ctx.principal,
            tenant_id=project.tenant_id,
            project_id=project.project_id,
            command=command,
            idempotency_key=uuid4(),
        )
    assert failure.value.code == (
        "project_revision_conflict"
        if guard == "project_revision"
        else "tenant_lock_required"
        if guard == "tenant_lock"
        else "metadata_revision_conflict"
    )
    if guard == "blank_record_lock":
        assert ctx.command(record_type) == command


@pytest.mark.asyncio
async def test_import_rejects_an_active_workflow(import_context: ImportContext) -> None:
    ctx = import_context
    _create_run(ctx.fixture, ctx.project, start=False)
    with pytest.raises(WorkbenchError) as failure:
        await ctx.service.review_records(
            ctx.principal,
            tenant_id=ctx.project.tenant_id,
            project_id=ctx.project.project_id,
            command=ctx.command("attribute"),
            idempotency_key=uuid4(),
        )
    assert failure.value.code == "tenant_workflow_conflict"


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", ["object", "attribute"])
@pytest.mark.parametrize(
    "description",
    ["x" * 2001, "界" * 667, "Invalid\x01text"],
    ids=["too_long", "too_many_utf8_bytes", "control_character"],
)
async def test_import_validates_canonical_source_without_partial_writes(
    import_context: ImportContext, record_type: RecordType, description: str
) -> None:
    ctx = import_context
    with ctx.fixture.connect_owner() as connection:
        connection.execute(
            "UPDATE core.object SET object_description=%s WHERE object_id=%s"
            if record_type == "object"
            else "UPDATE core.attribute SET attribute_description=%s WHERE attribute_id=%s",
            (description, ctx.pairs[-1][0 if record_type == "object" else 1]),
        )
    command = ctx.command(record_type)
    with pytest.raises(InvalidRequestError):
        await ctx.service.review_records(
            ctx.principal,
            tenant_id=ctx.project.tenant_id,
            project_id=ctx.project.project_id,
            command=command,
            idempotency_key=uuid4(),
        )
    assert ctx.command(record_type) == command
