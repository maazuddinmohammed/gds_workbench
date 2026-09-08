"""Catalog-to-review HTTP round trip on fixture-created disposable PostgreSQL."""

# pyright: reportPrivateUsage=false
from uuid import uuid4

import httpx2
import pytest
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata import DatabaseMetadataService, PostgresMetadataRepository
from gds_workbench_api.features.metadata.review import DatabaseMetadataReviewService
from gds_workbench_api.main import create_app

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.web_backend.test_database_model_change_sets import _seed_profile_model


@pytest.mark.parametrize("record_type", ["object", "attribute"])
async def test_catalog_review_all_actions_and_replay_preserve_physical_content_and_model(
    web_postgres_database: DisposablePostgres,
    record_type: str,
) -> None:
    model_id, tenant_id, attribute_id, entra_tenant, entra_object, _ = _seed_profile_model(
        web_postgres_database
    )
    with web_postgres_database.connect_owner() as connection:
        attribute_before = require_row(
            connection.execute(
                "SELECT * FROM core.attribute WHERE attribute_id=%s", (attribute_id,)
            ).fetchone()
        )
        object_id = attribute_before["object_id"]
        object_before = require_row(
            connection.execute(
                "SELECT * FROM core.object WHERE object_id=%s", (object_id,)
            ).fetchone()
        )
        model_before = require_row(
            connection.execute(
                "SELECT model_revision FROM model.model WHERE model_id=%s", (model_id,)
            ).fetchone()
        )
        assert require_row(
            connection.execute(
                "SELECT acquired FROM security.acquire_tenant_lock(%s,%s,'user',%s,60,%s)",
                (entra_tenant, entra_object, tenant_id, "Physical review fixture"),
            ).fetchone()
        )["acquired"]
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(), pool_min=1, pool_max=2, pool_timeout_seconds=5
    )
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV, local_tenant_id=entra_tenant, local_principal_object_id=entra_object
        ),
        metadata_service=DatabaseMetadataService(
            database=database,
            repository=PostgresMetadataRepository(),
            authorizer=AuthorizationService(),
            cursor_signing_key=b"fixture-review-catalog-key-32-byte",
        ),
        metadata_review_service=DatabaseMetadataReviewService(database=database),
    )
    await database.open()
    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://fixture.invalid"
        ) as client:
            detail_url = f"/api/v1/tenants/{tenant_id}/metadata/objects/{object_id}"
            initial = await client.get(detail_url)
            assert initial.status_code == 200
            record_id = object_id if record_type == "object" else attribute_id
            record = initial.json() if record_type == "object" else initial.json()["attributes"][0]
            revision = record["review_revision"]
            for action, active, locked in (
                ("lock", True, True),
                ("unlock", True, False),
                ("deactivate", False, False),
                ("reactivate", True, False),
            ):
                body = {
                    "record_type": record_type,
                    "action": action,
                    "records": [{"record_id": record_id, "expected_revision": revision}],
                }
                headers = {"Idempotency-Key": str(uuid4())}
                response = await client.post(
                    f"/api/v1/tenants/{tenant_id}/metadata/review", json=body, headers=headers
                )
                assert response.status_code == 200
                result = response.json()
                assert result["action_count"] == 1
                reviewed = result["records"][0]
                assert reviewed["is_active"] is active and reviewed["is_locked"] is locked
                assert reviewed["review_revision"] != revision
                replay = await client.post(
                    f"/api/v1/tenants/{tenant_id}/metadata/review", json=body, headers=headers
                )
                assert replay.status_code == 200 and replay.json() == result
                stale = await client.post(
                    f"/api/v1/tenants/{tenant_id}/metadata/review",
                    json=body,
                    headers={"Idempotency-Key": str(uuid4())},
                )
                assert stale.status_code == 409
                assert stale.json()["error"]["code"] == "metadata_revision_conflict"
                fresh = await client.get(detail_url)
                assert fresh.status_code == 200
                record = fresh.json() if record_type == "object" else fresh.json()["attributes"][0]
                assert record["review_revision"] == reviewed["review_revision"]
                assert record["is_active"] is active and record["is_locked"] is locked
                revision = reviewed["review_revision"]
    finally:
        await database.close()
    with web_postgres_database.connect_owner() as connection:
        attribute_after = require_row(
            connection.execute(
                "SELECT * FROM core.attribute WHERE attribute_id=%s", (attribute_id,)
            ).fetchone()
        )
        object_after = require_row(
            connection.execute(
                "SELECT * FROM core.object WHERE object_id=%s", (object_id,)
            ).fetchone()
        )
        assert (
            require_row(
                connection.execute(
                    "SELECT model_revision FROM model.model WHERE model_id=%s", (model_id,)
                ).fetchone()
            )
            == model_before
        )
        assert (
            require_row(
                connection.execute(
                    "SELECT count(*) AS count FROM application.metadata_review_event "
                    "WHERE tenant_id=%s",
                    (tenant_id,),
                ).fetchone()
            )["count"]
            == 4
        )
    for before, after in ((object_before, object_after), (attribute_before, attribute_after)):
        assert {
            key: value for key, value in before.items() if key not in {"updated_time", "updated_by"}
        } == {
            key: value for key, value in after.items() if key not in {"updated_time", "updated_by"}
        }
