"""Authorized shared models retain input ownership and reject access leakage."""

from dataclasses import replace
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.application.change_sets.model_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import (
    ModelReadContext,
    authorize_model_read,
)
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError, TenantNotFoundError
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    select_snapshot_datasets,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import complete_model_graph
from tests.mcp.test_database_authorization import _seed_user_actor
from tests.mcp.test_database_metadata_snapshot_selection import _decode_rows
from tests.mcp.test_database_model_change_set_round_trip import (
    _replace_codes,
    _seed_model_foundation,
)


@pytest.mark.asyncio
async def test_cross_tenant_scope_requires_source_access_and_keeps_target_ownership(
    postgres_database: DisposablePostgres,
) -> None:
    first, second = f"SHARED_{uuid4().hex}", f"SOURCE_{uuid4().hex}"
    model_id, owner_id = _seed_model_foundation(postgres_database, code_prefix=first)
    _, source_id = _seed_model_foundation(postgres_database, code_prefix=second)
    source_records = _replace_codes(complete_model_graph(), code_prefix=second)["model_input_scope"]
    model = ModelReadContext(model_id, owner_id, "Model Tool Round Trip", 1)
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        async with database.write_transaction() as transaction:
            snapshot = await build_model_snapshot(transaction, model)
            owned = await load_model_physical_scope(transaction, model)
            assert not validate_future_graph(
                snapshot=snapshot,
                staged_documents={"model_input_scope": source_records},
                physical_scope=owned,
            ).valid
            permitted = await load_model_physical_scope(
                transaction,
                replace(model, readable_source_tenant_ids=(owner_id, source_id)),
            )
            result = validate_future_graph(
                snapshot=snapshot,
                staged_documents={"model_input_scope": source_records},
                physical_scope=permitted,
            )
            assert result.valid
            # Read permission for another Tenant's inputs never makes its targets ours.
            assert permitted.logical_mapping_target_objects == owned.logical_mapping_target_objects
            assert (
                permitted.dimensional_mapping_target_objects
                == owned.dimensional_mapping_target_objects
            )
            await ModelMaterializer(
                transaction, model_id, "a" * 64, readable_source_tenant_ids=(owner_id, source_id)
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
                display_name="Model reader",
                email=f"{uuid4().hex}@example.invalid",
                entra_tenant_id=identity_tenant,
                entra_object_id=identity_object,
                tenant_role="viewer",
            )
        principal = RequestPrincipal(ActorKind.HUMAN, identity_tenant, identity_object)
        authorizer = AuthorizationService()
        async with database.read_transaction() as transaction:
            with pytest.raises(InvalidRequestError, match="Source Tenant"):
                await authorize_model_read(
                    transaction,
                    authorizer=authorizer,
                    principal=principal,
                    model_id=model_id,
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
            authorized = await authorize_model_read(
                transaction,
                authorizer=authorizer,
                principal=principal,
                model_id=model_id,
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
                dataset.definition.name: _decode_rows(dataset) for dataset in selected.datasets
            }
            source_owners = {row["source_tenant_code"] for row in records["source_object"]}
            assert len(source_owners) == 2
            assert all(
                row["source_tenant_code"] == selected.tenant_code
                for row in records["silver_object"]
            )
            refreshed = await build_model_snapshot(transaction, authorized)
            assert refreshed is not None
    finally:
        await database.close()
