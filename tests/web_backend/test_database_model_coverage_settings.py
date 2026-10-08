"""Persist coverage settings through governed commands in a disposable database."""

# pyright: reportPrivateUsage=false
from uuid import uuid4

import pytest
from psycopg import errors

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.model_read import authorize_model_read
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.models.command_contracts import (
    CompleteModelRequest,
    UpdateModelRequest,
)
from gds_workbench_api.features.models.command_service import (
    DatabaseModelCommandService,
)
from gds_workbench_api.features.models.service import DatabaseModelService
from gds_workbench_api.features.workflows.authoring.gold_policy import (
    effective_gold_templates,
)
from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _seed_model_foundation,
)


async def test_database_defaults_custom_thresholds_reset_and_snapshot(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    model_id, tenant_id = _seed_model_foundation(
        fixture, code_prefix="COVERAGE_" + uuid4().hex
    )
    _acquire_tenant_lock(fixture, tenant_id)
    with fixture.connect_owner() as connection:
        connection.execute(
            "UPDATE security.tenant_principal_access SET tenant_role='tenant_admin' "
            "WHERE tenant_id=%s",
            (tenant_id,),
        )
        defaults = connection.execute(
            "SELECT logical_coverage_threshold_percent, dimensional_coverage_threshold_percent "
            "FROM model.model WHERE model_id=%s",
            (model_id,),
        ).fetchone()
        assert defaults == {
            "logical_coverage_threshold_percent": 70,
            "dimensional_coverage_threshold_percent": 60,
        }
        for column in (
            "logical_coverage_threshold_percent",
            "dimensional_coverage_threshold_percent",
        ):
            for invalid in (0, 101):
                with pytest.raises(errors.CheckViolation), connection.transaction():
                    connection.execute(
                        f"UPDATE model.model SET {column}=%s WHERE model_id=%s",
                        (invalid, model_id),
                    )

    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    authorizer = AuthorizationService()
    commands = DatabaseModelCommandService(
        database=database,
        authorizer=authorizer,
        agent_capability_registry=load_default_agent_capabilities(),
    )
    reads = DatabaseModelService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=b"fixture-coverage-cursor-key-32-byte",
    )
    principal = StaticIdentityProvider().request_principal(None)
    await database.open()
    try:
        created = await commands.create_model(
            principal,
            tenant_id=tenant_id,
            request=CompleteModelRequest(model_name="Coverage settings"),
        )
        detail = await reads.read_model(
            principal, tenant_id=tenant_id, model_id=created.model_id
        )
        assert (
            detail.logical_coverage_threshold_percent,
            detail.dimensional_coverage_threshold_percent,
        ) == (70, 60)
        technical, audit = effective_gold_templates(None, None)
        updated = await commands.update_model(
            principal,
            tenant_id=tenant_id,
            model_id=created.model_id,
            request=UpdateModelRequest.model_validate(
                {
                    "model_name": detail.model_name,
                    "expected_model_revision": detail.model_revision,
                    "logical_coverage_threshold_percent": 69,
                    "dimensional_coverage_threshold_percent": 83,
                    "gold_model_technical_columns_template": technical,
                    "gold_model_audit_columns_template": audit,
                }
            ),
        )
        detail = await reads.read_model(
            principal, tenant_id=tenant_id, model_id=created.model_id
        )
        assert (
            detail.logical_coverage_threshold_percent,
            detail.dimensional_coverage_threshold_percent,
        ) == (69, 83)
        assert detail.gold_model_technical_columns_template is None
        assert isinstance(detail.gold_model_audit_columns_template, dict)
        assert detail.gold_model_audit_columns_template["type_2"] == technical["type_2"]
        async with database.read_transaction() as transaction:
            context = await authorize_model_read(
                transaction,
                authorizer=authorizer,
                principal=principal,
                model_id=created.model_id,
            )
            snapshot = await build_model_snapshot(transaction, context)
        assert (
            snapshot.model_input_scope.details.logical_coverage_threshold_percent == 69
        )
        assert (
            snapshot.model_input_scope.details.dimensional_coverage_threshold_percent
            == 83
        )
        reset = await commands.update_model(
            principal,
            tenant_id=tenant_id,
            model_id=created.model_id,
            request=UpdateModelRequest(
                model_name=detail.model_name,
                expected_model_revision=updated.model_revision,
            ),
        )
        assert reset.model_revision == updated.model_revision + 1
        detail = await reads.read_model(
            principal, tenant_id=tenant_id, model_id=created.model_id
        )
        assert (
            detail.logical_coverage_threshold_percent,
            detail.dimensional_coverage_threshold_percent,
        ) == (70, 60)
    finally:
        await database.close()
