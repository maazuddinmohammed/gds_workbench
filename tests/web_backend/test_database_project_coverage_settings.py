"""Persist coverage settings through governed commands in a disposable database."""

# pyright: reportPrivateUsage=false
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.project_read import authorize_project_read
from gds_etl_workbench.application.project_snapshot import build_project_snapshot
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.projects.command_contracts import (
    CompleteProjectRequest,
    ProjectRevisionConflictError,
    UpdateProjectRequest,
)
from gds_workbench_api.features.projects.command_service import (
    DatabaseProjectCommandService,
)
from gds_workbench_api.features.projects.service import DatabaseProjectService
from gds_workbench_api.features.workflows.authoring.gold_policy import (
    effective_gold_templates,
)
from psycopg import errors

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_project_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _seed_project_foundation,
)


async def test_database_defaults_custom_thresholds_reset_and_snapshot(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    project_id, tenant_id = _seed_project_foundation(
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
            "SELECT logical_coverage_threshold_percent, dimensional_coverage_threshold_percent, "
            "logical_enforce_coverage_threshold, dimensional_enforce_coverage_threshold "
            "FROM project.project WHERE project_id=%s",
            (project_id,),
        ).fetchone()
        assert defaults == {
            "logical_coverage_threshold_percent": 70,
            "dimensional_coverage_threshold_percent": 60,
            "logical_enforce_coverage_threshold": False,
            "dimensional_enforce_coverage_threshold": False,
        }
        for column in (
            "logical_coverage_threshold_percent",
            "dimensional_coverage_threshold_percent",
        ):
            for invalid in (0, 101):
                with pytest.raises(errors.CheckViolation), connection.transaction():
                    connection.execute(
                        f"UPDATE project.project SET {column}=%s WHERE project_id=%s",
                        (invalid, project_id),
                    )

    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    authorizer = AuthorizationService()
    commands = DatabaseProjectCommandService(
        database=database,
        authorizer=authorizer,
        agent_capability_registry=load_default_agent_capabilities(),
    )
    reads = DatabaseProjectService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=b"fixture-coverage-cursor-key-32-byte",
    )
    principal = StaticIdentityProvider().request_principal(None)
    await database.open()
    try:
        created = await commands.create_project(
            principal,
            tenant_id=tenant_id,
            request=CompleteProjectRequest(project_name="Coverage settings"),
        )
        detail = await reads.read_project(
            principal, tenant_id=tenant_id, project_id=created.project_id
        )
        assert (
            detail.logical_coverage_threshold_percent,
            detail.dimensional_coverage_threshold_percent,
        ) == (70, 60)
        assert detail.logical_enforce_coverage_threshold is False
        assert detail.dimensional_enforce_coverage_threshold is False
        technical, audit = effective_gold_templates(None, None)
        updated = await commands.update_project(
            principal,
            tenant_id=tenant_id,
            project_id=created.project_id,
            request=UpdateProjectRequest.model_validate(
                {
                    "project_name": detail.project_name,
                    "expected_project_revision": detail.project_revision,
                    "logical_coverage_threshold_percent": 69,
                    "dimensional_coverage_threshold_percent": 83,
                    "logical_enforce_coverage_threshold": True,
                    "dimensional_enforce_coverage_threshold": False,
                    "gold_model_technical_columns_template": technical,
                    "gold_model_audit_columns_template": audit,
                }
            ),
        )
        detail = await reads.read_project(
            principal, tenant_id=tenant_id, project_id=created.project_id
        )
        assert (
            detail.logical_coverage_threshold_percent,
            detail.dimensional_coverage_threshold_percent,
        ) == (69, 83)
        assert detail.logical_enforce_coverage_threshold is True
        assert detail.dimensional_enforce_coverage_threshold is False
        assert detail.gold_model_technical_columns_template is None
        assert isinstance(detail.gold_model_audit_columns_template, dict)
        assert detail.gold_model_audit_columns_template["type_2"] == technical["type_2"]
        async with database.read_transaction() as transaction:
            context = await authorize_project_read(
                transaction,
                authorizer=authorizer,
                principal=principal,
                project_id=created.project_id,
            )
            snapshot = await build_project_snapshot(transaction, context)
        assert (
            snapshot.project_input_scope.details.logical_coverage_threshold_percent
            == 69
        )
        assert (
            snapshot.project_input_scope.details.dimensional_coverage_threshold_percent
            == 83
        )
        assert (
            snapshot.project_input_scope.details.logical_enforce_coverage_threshold
            is True
        )
        assert (
            snapshot.project_input_scope.details.dimensional_enforce_coverage_threshold
            is False
        )
        reset = await commands.update_project(
            principal,
            tenant_id=tenant_id,
            project_id=created.project_id,
            request=UpdateProjectRequest(
                project_name=detail.project_name,
                expected_project_revision=updated.project_revision,
            ),
        )
        assert reset.project_revision == updated.project_revision + 1
        detail = await reads.read_project(
            principal, tenant_id=tenant_id, project_id=created.project_id
        )
        assert (
            detail.logical_coverage_threshold_percent,
            detail.dimensional_coverage_threshold_percent,
        ) == (70, 60)
        assert detail.logical_enforce_coverage_threshold is False
        assert detail.dimensional_enforce_coverage_threshold is False
    finally:
        await database.close()


async def test_database_coverage_enforcement_changes_are_revision_fenced(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    project_id, tenant_id = _seed_project_foundation(
        fixture,
        code_prefix="ENFORCE_" + uuid4().hex,
    )
    _acquire_tenant_lock(fixture, tenant_id)
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    commands = DatabaseProjectCommandService(
        database=database,
        authorizer=authorizer,
        agent_capability_registry=load_default_agent_capabilities(),
    )
    reads = DatabaseProjectService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=b"fixture-coverage-cursor-key-32-byte",
    )
    principal = StaticIdentityProvider().request_principal(None)
    await database.open()
    try:
        before = await reads.read_project(
            principal, tenant_id=tenant_id, project_id=project_id
        )
        command = UpdateProjectRequest(
            project_name=before.project_name,
            expected_project_revision=before.project_revision,
            logical_enforce_coverage_threshold=True,
            dimensional_enforce_coverage_threshold=True,
        )
        updated = await commands.update_project(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            request=command,
        )
        assert updated.project_revision == before.project_revision + 1
        after = await reads.read_project(
            principal, tenant_id=tenant_id, project_id=project_id
        )
        assert after.logical_enforce_coverage_threshold is True
        assert after.dimensional_enforce_coverage_threshold is True
        with pytest.raises(ProjectRevisionConflictError):
            await commands.update_project(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                request=command,
            )
        unchanged = await commands.update_project(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            request=command.model_copy(
                update={"expected_project_revision": updated.project_revision}
            ),
        )
        assert unchanged.project_revision == updated.project_revision
    finally:
        await database.close()
