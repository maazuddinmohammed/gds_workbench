"""Authorized shared projects retain input ownership and reject access leakage."""

from dataclasses import replace
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.project import (
    load_project_physical_scope,
)
from gds_etl_workbench.application.change_sets.project_apply import ProjectMaterializer
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.metadata_snapshot.selection import (
    select_snapshot_datasets,
)
from gds_etl_workbench.application.project_read import (
    ProjectReadContext,
    authorize_project_read,
)
from gds_etl_workbench.application.project_snapshot import build_project_snapshot
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError, TenantNotFoundError

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.project_test_fixtures import complete_project_graph
from tests.mcp.test_database_authorization import _seed_user_actor
from tests.mcp.test_database_metadata_snapshot_selection import _decode_rows
from tests.mcp.test_database_project_change_set_round_trip import (
    _replace_codes,
    _seed_project_foundation,
)


@pytest.mark.asyncio
async def test_cross_tenant_scope_requires_source_access_and_keeps_target_ownership(
    postgres_database: DisposablePostgres,
) -> None:
    first, second = f"SHARED_{uuid4().hex}", f"SOURCE_{uuid4().hex}"
    project_id, owner_id = _seed_project_foundation(
        postgres_database, code_prefix=first
    )
    _, source_id = _seed_project_foundation(postgres_database, code_prefix=second)
    source_records = _replace_codes(complete_project_graph(), code_prefix=second)[
        "project_input_scope"
    ]
    project = ProjectReadContext(project_id, owner_id, "Project Tool Round Trip", 1)
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        async with database.write_transaction() as transaction:
            snapshot = await build_project_snapshot(transaction, project)
            owned = await load_project_physical_scope(transaction, project)
            assert not validate_future_graph(
                snapshot=snapshot,
                staged_documents={"project_input_scope": source_records},
                physical_scope=owned,
            ).valid
            permitted = await load_project_physical_scope(
                transaction,
                replace(project, readable_source_tenant_ids=(owner_id, source_id)),
            )
            result = validate_future_graph(
                snapshot=snapshot,
                staged_documents={"project_input_scope": source_records},
                physical_scope=permitted,
            )
            assert result.valid
            # Additional input read permission does not change the Project owner.
            assert permitted.project_tenant_code == owned.project_tenant_code
            assert permitted.project_input_objects > owned.project_input_objects
            await ProjectMaterializer(
                transaction,
                project_id,
                "a" * 64,
                readable_source_tenant_ids=(owner_id, source_id),
            ).apply(result.records)
        identity_tenant, identity_object = uuid4(), uuid4()
        with postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.tenant SET tenant_visibility = %s WHERE tenant_id = ANY(%s)",
                ("private", [owner_id, source_id]),
            )
            actor_id = _seed_user_actor(
                connection,
                tenant_id=owner_id,
                display_name="Project reader",
                email=f"{uuid4().hex}@example.invalid",
                entra_tenant_id=identity_tenant,
                entra_object_id=identity_object,
                tenant_role="viewer",
            )
        principal = RequestPrincipal(ActorKind.HUMAN, identity_tenant, identity_object)
        authorizer = AuthorizationService()
        async with database.read_transaction() as transaction:
            with pytest.raises(InvalidRequestError, match="Source Tenant"):
                await authorize_project_read(
                    transaction,
                    authorizer=authorizer,
                    principal=principal,
                    project_id=project_id,
                )
            with pytest.raises(TenantNotFoundError):
                await select_snapshot_datasets(
                    transaction,
                    tenant_id=owner_id,
                    source_tenant_ids=(source_id,),
                    request_principal=principal,
                    authorizer=authorizer,
                )
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """INSERT INTO security.tenant_principal_access
                (tenant_id, principal_id, tenant_role, granted_by_principal_id)
                VALUES (%s, %s, 'viewer', %s)""",
                (source_id, actor_id, actor_id),
            )
        async with database.read_transaction() as transaction:
            authorized = await authorize_project_read(
                transaction,
                authorizer=authorizer,
                principal=principal,
                project_id=project_id,
            )
            assert source_id in authorized.readable_source_tenant_ids
            selected = await select_snapshot_datasets(
                transaction,
                tenant_id=owner_id,
                source_tenant_ids=(source_id,),
                request_principal=principal,
                authorizer=authorizer,
            )
            records = {
                dataset.definition.name: _decode_rows(dataset)
                for dataset in selected.datasets
            }
            source_owners = {
                row["source_tenant_code"] for row in records["source_object"]
            }
            assert len(source_owners) == 2
            assert all(
                row["source_tenant_code"] == selected.tenant_code
                for row in records["silver_object"]
            )
            refreshed = await build_project_snapshot(transaction, authorized)
            assert refreshed is not None
    finally:
        await database.close()
