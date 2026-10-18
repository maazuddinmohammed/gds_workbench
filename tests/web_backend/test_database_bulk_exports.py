"""Bulk ZIP routes use the web role and one exact Project/layer/revision."""

# Fixture imports reuse only disposable databases and synthetic identities.
# pyright: reportPrivateUsage=false
import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import httpx2
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.code_generation import DatabaseCodeGenerationService
from gds_workbench_api.features.validation import DatabaseValidationReadService
from gds_workbench_api.main import create_app

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.conftest import (
    bootstrap_postgres_database as bootstrap_postgres_database,
)
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_global_prompt_seed import _apply_sql
from tests.web_backend.test_database_agent_workflow_pipeline import (
    pipeline_database as pipeline_database,
)


async def test_bulk_export_routes_preserve_active_stale_files_and_exact_scope(
    pipeline_database: DisposablePostgres,
) -> None:
    fixture = pipeline_database
    seed_root = Path(__file__).parents[2] / "database" / "seed"
    _apply_sql(fixture, (seed_root / "01_metadata_snapshot_demo.sql").read_text())
    seed = (seed_root / "08_local_workbench_review.sql").read_text()
    local_guard = "current_database() !~ '^gds_local_[0-9a-f]{12}$'"
    assert seed.count(local_guard) == 1
    seed = seed.replace(local_guard, f"current_database() <> '{fixture.database}'")
    _apply_sql(fixture, seed)
    entra_tenant_id, entra_object_id = uuid4(), uuid4()
    with fixture.connect_owner() as connection:
        project = require_row(
            connection.execute(
                "SELECT project_id,tenant_id,project_revision FROM project.project "
                "WHERE project_name='Customer Orders 360'"
            ).fetchone()
        )
        principal = require_row(
            connection.execute(
                "INSERT INTO security.principal "
                "(principal_type,principal_display_name,principal_email) "
                "VALUES ('user','Export fixture viewer',%s) RETURNING principal_id",
                (f"export_{entra_object_id.hex}@example.test",),
            ).fetchone()
        )
        connection.execute(
            "INSERT INTO security.entra_principal_identity "
            "(principal_id,principal_type,entra_tenant_id,entra_object_id) "
            "VALUES (%s,'user',%s,%s)",
            (principal["principal_id"], entra_tenant_id, entra_object_id),
        )
        connection.execute(
            "INSERT INTO security.tenant_principal_access "
            "(tenant_id,principal_id,tenant_role,granted_by_principal_id) "
            "VALUES (%s,%s,'viewer',%s)",
            (project["tenant_id"], principal["principal_id"], principal["principal_id"]),
        )
        # Active files remain downloadable when their Mapping context is unavailable.
        connection.execute(
            "UPDATE workflow.mapping_object SET object_mapping_status='inactive' "
            "WHERE project_id=%s AND modeled_entity_type='logical_entity'",
            (project["project_id"],),
        )
        connection.execute(
            "UPDATE workflow.generated_code SET generated_code_status='inactive' "
            "WHERE generated_code_id=(SELECT max(generated_code_id) FROM workflow.generated_code "
            "WHERE project_id=%s AND modeled_entity_type='dimensional_entity')",
            (project["project_id"],),
        )
        connection.execute(
            "UPDATE workflow.validation_check SET is_active=FALSE "
            "WHERE validation_check_id=(SELECT max(check_record.validation_check_id) "
            "FROM workflow.validation_check AS check_record "
            "JOIN workflow.validation_group AS group_record USING(validation_group_id) "
            "WHERE group_record.project_id=%s)",
            (project["project_id"],),
        )
        artifacts = connection.execute(
            "SELECT generated_code_id,modeled_entity_type,generated_code_content "
            "FROM workflow.generated_code WHERE project_id=%s AND generated_code_status='active'",
            (project["project_id"],),
        ).fetchall()
        check_rows = connection.execute(
            "SELECT check_record.validation_check_id,check_record.validation_query_sql "
            "FROM workflow.validation_check AS check_record "
            "JOIN workflow.validation_group AS group_record USING(validation_group_id) "
            "WHERE group_record.project_id=%s AND group_record.is_active "
            "AND check_record.is_active",
            (project["project_id"],),
        ).fetchall()
        other = require_row(
            connection.execute(
                "INSERT INTO project.project(tenant_id,project_name) "
                "VALUES (%s,'Empty export Project') "
                "RETURNING project_id,project_revision",
                (project["tenant_id"],),
            ).fetchone()
        )
        project = require_row(
            connection.execute(
                "SELECT project_id,tenant_id,project_revision FROM project.project "
                "WHERE project_id=%s",
                (project["project_id"],),
            ).fetchone()
        )
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    authorizer = AuthorizationService()
    code_service = DatabaseCodeGenerationService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    validation_service = DatabaseValidationReadService(database=database, authorizer=authorizer)
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV, local_tenant_id=entra_tenant_id, local_principal_object_id=entra_object_id
        ),
        code_generation_service=code_service,
        validation_read_service=validation_service,
    )
    await database.open()
    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://fixture.invalid"
        ) as client:
            for layer in ("logical_entity", "dimensional_entity"):
                command = {
                    "entity_type": layer,
                    "expected_project_revision": project["project_revision"],
                }
                expected = {
                    row["generated_code_id"]: row["generated_code_content"]
                    for row in artifacts
                    if row["modeled_entity_type"] == layer
                }
                assert expected
                for workflow in ("code-generation", "validation"):
                    base = (
                        f"/api/v1/tenants/{project['tenant_id']}/projects/{project['project_id']}"
                    )
                    path = f"{base}/{workflow}/downloads/all.zip"
                    response = await client.post(path, json=command)
                    assert response.status_code == 200
                    with ZipFile(BytesIO(response.content)) as archive:
                        manifest = json.loads(archive.read("manifest.json"))
                        assert manifest["entity_type"] == layer
                        assert manifest["project_revision"] == project["project_revision"]
                        if workflow == "code-generation":
                            assert {
                                row["generated_sql_artifact_id"] for row in manifest["artifacts"]
                            } == set(expected)
                            for row in manifest["artifacts"]:
                                assert (
                                    archive.read(row["filename"])
                                    == expected[row["generated_sql_artifact_id"]].encode()
                                )
                                if layer == "logical_entity":
                                    assert row["artifact_is_current"] is False
                        else:
                            checks = [
                                check for group in manifest["groups"] for check in group["checks"]
                            ]
                            assert {check["validation_check_id"] for check in checks} == {
                                row["validation_check_id"] for row in check_rows
                            }
                            assert len(checks) == 2
                            for check in checks:
                                assert check["validation_comparison_operator"] == "equal"
                                assert check["validation_comparison_value"] == 0
                                assert archive.read(check["query_file"])
                    stale = await client.post(
                        path,
                        json={
                            **command,
                            "expected_project_revision": project["project_revision"] + 1,
                        },
                    )
                    assert stale.status_code == 409
                    assert stale.json()["error"]["code"] == "project_revision_conflict"
                    empty = await client.post(
                        f"/api/v1/tenants/{project['tenant_id']}/projects/{other['project_id']}/"
                        f"{workflow}/downloads/all.zip",
                        json={**command, "expected_project_revision": other["project_revision"]},
                    )
                    assert empty.status_code == 400
                    assert empty.json()["error"]["code"] == (
                        "generated_sql_export_empty"
                        if workflow == "code-generation"
                        else "validation_export_empty"
                    )
                    denied = await client.post(
                        f"/api/v1/tenants/999999/projects/{project['project_id']}/"
                        f"{workflow}/downloads/all.zip",
                        json=command,
                    )
                    assert denied.status_code == 404
                    assert denied.json()["error"]["code"].endswith("_not_found")
        unauthorized_app = create_app(
            identity_provider=IdentityProvider(
                AuthMode.DEV, local_tenant_id=entra_tenant_id, local_principal_object_id=uuid4()
            ),
            code_generation_service=code_service,
            validation_read_service=validation_service,
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=unauthorized_app), base_url="http://fixture.invalid"
        ) as client:
            for workflow in ("code-generation", "validation"):
                response = await client.post(
                    f"/api/v1/tenants/{project['tenant_id']}/projects/{project['project_id']}/"
                    f"{workflow}/downloads/all.zip",
                    json={
                        "entity_type": "logical_entity",
                        "expected_project_revision": project["project_revision"],
                    },
                )
                assert response.status_code == 403
                assert response.json()["error"]["code"] == "authorization_denied"
    finally:
        await database.close()
