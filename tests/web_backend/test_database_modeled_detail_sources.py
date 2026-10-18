"""Detail APIs preserve source status for physical and Logical evidence."""

# Fixture imports reuse only disposable databases and synthetic identities.
# pyright: reportPrivateUsage=false
from pathlib import Path

import httpx2
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.dimensional import DatabaseDimensionalService
from gds_workbench_api.features.logical import DatabaseLogicalService
from gds_workbench_api.main import create_app

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.conftest import (
    bootstrap_postgres_database as bootstrap_postgres_database,
)
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_global_prompt_seed import (
    ENTRA_OBJECT_ID,
    ENTRA_TENANT_ID,
    _apply_sql,
)
from tests.web_backend.test_database_agent_workflow_pipeline import (
    pipeline_database as pipeline_database,
)


async def test_seeded_modeled_detail_apis_preserve_non_context_source_status(
    pipeline_database: DisposablePostgres,
) -> None:
    fixture = pipeline_database
    seed_root = Path(__file__).parents[2] / "database" / "seed"
    _apply_sql(fixture, (seed_root / "01_metadata_snapshot_demo.sql").read_text())
    seed = (seed_root / "08_local_workbench_review.sql").read_text()
    local_guard = "current_database() !~ '^gds_local_[0-9a-f]{12}$'"
    assert seed.count(local_guard) == 1
    # Keep the seed guarded by this exact verified disposable fixture database.
    seed = seed.replace(local_guard, f"current_database() <> '{fixture.database}'")
    _apply_sql(fixture, seed)
    with fixture.connect_owner() as connection:
        project = require_row(
            connection.execute(
                "SELECT project_id,tenant_id FROM project.project "
                "WHERE project_name='Customer Orders 360'"
            ).fetchone()
        )
        details = connection.execute(
            """
            SELECT 'logical/entities' AS path, logical_entity_id AS record_id
              FROM workflow.logical_entity WHERE project_id=%s
            UNION ALL
            SELECT 'logical/attributes', logical_attribute_id
              FROM workflow.logical_attribute WHERE project_id=%s
            UNION ALL
            SELECT 'dimensional/objects', dimensional_entity_id
              FROM workflow.dimensional_entity WHERE project_id=%s
            UNION ALL
            SELECT 'dimensional/attributes', dimensional_attribute_id
              FROM workflow.dimensional_attribute WHERE project_id=%s
            """,
            (project["project_id"],) * 4,
        ).fetchall()
    assert {row["path"] for row in details} == {
        "logical/entities",
        "logical/attributes",
        "dimensional/objects",
        "dimensional/attributes",
    }
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    authorizer = AuthorizationService()
    signing_key = b"development-only-key-32-bytes-long"
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=ENTRA_TENANT_ID,
            local_principal_object_id=ENTRA_OBJECT_ID,
        ),
        logical_service=DatabaseLogicalService(
            database=database, authorizer=authorizer, cursor_signing_key=signing_key
        ),
        dimensional_service=DatabaseDimensionalService(
            database=database, authorizer=authorizer, cursor_signing_key=signing_key
        ),
    )
    source_types: set[str] = set()
    await database.open()
    try:
        readiness = await database.readiness()
        assert readiness.ready and readiness.code == "ready"
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://fixture.invalid"
        ) as client:
            for row in details:
                response = await client.get(
                    f"/api/v1/tenants/{project['tenant_id']}/projects/{project['project_id']}/"
                    f"{row['path']}/{row['record_id']}"
                )
                assert response.status_code == 200
                for source in response.json()["sources"]:
                    source_types.add(source["support_source_type"])
                    assert source["status"] == "active"
    finally:
        await database.close()
    assert {"object", "attribute", "logical_entity", "logical_attribute"} <= source_types
