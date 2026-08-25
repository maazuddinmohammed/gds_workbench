from typing import Protocol
from uuid import UUID, uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    DraftRevisionConflictError,
    MetadataChangeSetNotFoundError,
    TenantLockRequiredError,
)
from psycopg import Connection
from tests.mcp.test_database_metadata_change_set import (
    _seed_change_set_parents,  # pyright: ignore[reportPrivateUsage]
)

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata_change_sets.contracts import (
    CreateMetadataChangeSetRequest,
    ExpectedDraftRevisionRequest,
    StageMetadataChangeSetRequest,
    StageMetadataDatasetRequest,
)
from gds_workbench_api.features.metadata_change_sets.service import (
    DatabaseMetadataChangeSetService,
)


class DisposablePostgresFixture(Protocol):
    def connect_owner(self) -> Connection[dict[str, object]]: ...

    def web_runtime_dsn(self) -> str: ...


@pytest.mark.asyncio
async def test_web_metadata_change_set_preserves_lock_isolation_revision_and_apply(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000090")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000090")
    with web_postgres_database.connect_owner() as connection:
        tenant_id, principal_id = _seed_change_set_parents(
            connection,
            suffix="WEB_METADATA",
        )
        other_tenant_id, _other_principal_id = _seed_change_set_parents(
            connection,
            suffix="WEB_METADATA_OTHER",
        )
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id, principal_type, entra_tenant_id, entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id, principal_id, tenant_role, granted_by_principal_id
            ) VALUES (%s, %s, 'developer', %s), (%s, %s, 'developer', %s)
            """,
            (
                tenant_id,
                principal_id,
                principal_id,
                other_tenant_id,
                principal_id,
                principal_id,
            ),
        )
        system_type = connection.execute(
            """
            INSERT INTO reference.system_type (system_type_code, system_type_name)
            VALUES ('DATABASE_WEB_METADATA', 'Database Web Metadata')
            RETURNING system_type_id
            """
        ).fetchone()
        assert system_type is not None
        connection_type = connection.execute(
            """
            INSERT INTO reference.connection_type (
                connection_type_code, connection_type_name
            ) VALUES ('POSTGRES_WEB_METADATA', 'Postgres Web Metadata')
            RETURNING connection_type_id
            """
        ).fetchone()
        assert connection_type is not None
        system = connection.execute(
            """
            INSERT INTO core.system (system_code, system_name, system_type_id)
            VALUES ('CRM_WEB_METADATA', 'CRM Web Metadata', %s)
            RETURNING system_id
            """,
            (system_type["system_type_id"],),
        ).fetchone()
        assert system is not None
        connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id
            ) VALUES (%s, %s, 'MAIN', 'Main', %s)
            """,
            (
                tenant_id,
                system["system_id"],
                connection_type["connection_type_id"],
            ),
        )

    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    service = DatabaseMetadataChangeSetService(
        database=database,
        authorizer=AuthorizationService(),
    )
    await database.open()
    try:
        with pytest.raises(TenantLockRequiredError):
            await service.create_or_resume(
                principal,
                tenant_id=tenant_id,
                command=CreateMetadataChangeSetRequest(),
                idempotency_key=uuid4(),
            )

        with web_postgres_database.connect_owner() as connection:
            acquired = connection.execute(
                """
                SELECT acquired
                  FROM security.acquire_tenant_lock(
                      %s, %s, 'user', %s, 60, 'Web Metadata Change Set test'
                  )
                """,
                (entra_tenant_id, entra_object_id, tenant_id),
            ).fetchone()
        assert acquired == {"acquired": True}

        create_key = uuid4()
        created = await service.create_or_resume(
            principal,
            tenant_id=tenant_id,
            command=CreateMetadataChangeSetRequest(),
            idempotency_key=create_key,
        )
        resumed = await service.create_or_resume(
            principal,
            tenant_id=tenant_id,
            command=CreateMetadataChangeSetRequest(),
            idempotency_key=create_key,
        )
        assert resumed.metadata_change_set_id == created.metadata_change_set_id
        assert resumed.created is False
        assert resumed.draft_revision == created.draft_revision
        with pytest.raises(MetadataChangeSetNotFoundError):
            await service.get(
                principal,
                tenant_id=other_tenant_id,
                change_set_id=created.metadata_change_set_id,
                dataset=None,
            )

        record: dict[str, object] = {
            "tenant_code": "CHANGE_SET_TENANT_WEB_METADATA",
            "system_code": "CRM_WEB_METADATA",
            "copy_group_name": "CUSTOMERS",
            "copy_group_description": "Customer ingestion",
            "is_member_group_required": False,
            "is_active": True,
        }
        stale_command = StageMetadataChangeSetRequest(
            expected_draft_revision=2,
            changes=[
                StageMetadataDatasetRequest(
                    dataset="copy_group",
                    records=[record],
                )
            ],
        )
        with pytest.raises(DraftRevisionConflictError):
            await service.stage(
                principal,
                tenant_id=tenant_id,
                change_set_id=created.metadata_change_set_id,
                command=stale_command,
                idempotency_key=uuid4(),
            )

        staged = await service.stage(
            principal,
            tenant_id=tenant_id,
            change_set_id=created.metadata_change_set_id,
            command=stale_command.model_copy(update={"expected_draft_revision": 1}),
            idempotency_key=uuid4(),
        )
        reviewed = await service.validate(
            principal,
            tenant_id=tenant_id,
            change_set_id=created.metadata_change_set_id,
            command=ExpectedDraftRevisionRequest(expected_draft_revision=staged.draft_revision),
        )
        assert reviewed.valid is True
        assert reviewed.status == "validated"

        applied = await service.apply(
            principal,
            tenant_id=tenant_id,
            change_set_id=created.metadata_change_set_id,
            command=ExpectedDraftRevisionRequest(expected_draft_revision=staged.draft_revision),
            idempotency_key=uuid4(),
        )
    finally:
        await database.close()

    assert applied.applied is True
    assert applied.status == "applied"
    assert applied.action_count == 1
    with web_postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT copy_group.copy_group_name,
                   copy_group.copy_group_description,
                   copy_group.is_active
              FROM core.copy_group AS copy_group
             WHERE copy_group.tenant_id = %s
            """,
            (tenant_id,),
        ).fetchone()
    assert stored == {
        "copy_group_name": "CUSTOMERS",
        "copy_group_description": "Customer ingestion",
        "is_active": True,
    }
