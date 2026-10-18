# pyright: reportPrivateUsage=false
"""Context authoring preserves UUIDs, authorization, locks, revision and replay fencing."""

from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.context import DatabaseContextService
from gds_workbench_api.features.context.authoring import (
    SaveContextGroupRequest,
    SaveContextRecordRequest,
)
from gds_workbench_api.features.project_change_sets.contracts import (
    ReviewProjectRecordsRequest,
)
from gds_workbench_api.features.project_change_sets.service import (
    DatabaseProjectChangeSetService,
)
from gds_workbench_api.features.projects import ProjectRevisionConflictError

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_project_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _seed_project_foundation,
)


async def test_context_group_and_record_round_trip(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    prefix = f"CONTEXT_{uuid4().hex}"
    project_id, tenant_id = _seed_project_foundation(fixture, code_prefix=prefix)
    principal = StaticIdentityProvider().request_principal(None)
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    writes = DatabaseProjectChangeSetService(
        database=database, authorizer=AuthorizationService()
    )
    reads = DatabaseContextService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    with fixture.connect_owner() as connection:
        context_type = connection.execute(
            "SELECT context_type_id FROM reference.context_type WHERE name = 'Business Requirement'"
        ).fetchone()
        assert context_type is not None
    group = SaveContextGroupRequest(
        action="create",
        expected_project_revision=1,
        context_group_name="Finance requirements",
        context_type_id=context_type["context_type_id"],
        context_group_description="Reporting outcomes",
    )
    await database.open()
    try:
        with pytest.raises(WorkbenchError):
            await writes.save_context(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=group,
                idempotency_key=uuid4(),
            )
        _acquire_tenant_lock(fixture, tenant_id)
        group_key = uuid4()
        result = await writes.save_context(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=group,
            idempotency_key=group_key,
        )
        assert result.project_revision == 2
        assert (
            await writes.save_context(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=group,
                idempotency_key=group_key,
            )
            == result
        )
        with fixture.connect_owner() as connection:
            stored_group = connection.execute(
                "SELECT context_group_id FROM project.context_group WHERE project_id=%s",
                (project_id,),
            ).fetchone()
            assert stored_group is not None
        record = SaveContextRecordRequest(
            action="create",
            expected_project_revision=2,
            context_record_id=str(uuid4()),
            context_group_id=stored_group["context_group_id"],
            context_text="Report monthly net sales by customer segment.",
            source_reference="Finance requirements, section 2",
        )
        record_key = uuid4()
        result = await writes.save_context(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=record,
            idempotency_key=record_key,
        )
        assert result.project_revision == 3
        assert (
            await writes.save_context(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=record,
                idempotency_key=record_key,
            )
            == result
        )
        with pytest.raises(ProjectRevisionConflictError):
            await writes.save_context(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=record,
                idempotency_key=uuid4(),
            )
        with pytest.raises(InvalidRequestError):
            await writes.save_context(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=record.model_copy(update={"expected_project_revision": 3}),
                idempotency_key=uuid4(),
            )
        edited = record.model_copy(
            update={
                "action": "edit",
                "expected_project_revision": 3,
                "context_text": "Report net sales by month and customer segment.",
            }
        )
        assert (
            await writes.save_context(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=edited,
                idempotency_key=uuid4(),
            )
        ).project_revision == 4
        for action, revision in (
            ("lock", 4),
            ("unlock", 5),
            ("deactivate", 6),
            ("reactivate", 7),
        ):
            command = ReviewProjectRecordsRequest.model_validate(
                {
                    "dataset": "context_record",
                    "record_ids": [record.context_record_id],
                    "action": action,
                    "expected_project_revision": revision,
                }
            )
            assert (
                await writes.review_records(
                    principal,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    command=command,
                    idempotency_key=uuid4(),
                )
            ).project_revision == revision + 1
            if action == "lock":
                with pytest.raises(InvalidRequestError):
                    await writes.save_context(
                        principal,
                        tenant_id=tenant_id,
                        project_id=project_id,
                        command=edited.model_copy(
                            update={"expected_project_revision": 5}
                        ),
                        idempotency_key=uuid4(),
                    )
                with pytest.raises(InvalidRequestError):
                    await writes.save_context(
                        principal,
                        tenant_id=tenant_id,
                        project_id=project_id,
                        command=group.model_copy(
                            update={
                                "action": "edit",
                                "context_group_id": stored_group["context_group_id"],
                                "expected_project_revision": 5,
                                "context_group_description": "Changed scope",
                            }
                        ),
                        idempotency_key=uuid4(),
                    )
        detail = await reads.read_record(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            context_record_id=record.context_record_id,
        )
        assert detail.context_record_id == record.context_record_id
        assert detail.context_text == edited.context_text
        assert detail.source_reference == record.source_reference
        assert detail.status == "active" and not detail.is_locked
    finally:
        await database.close()
