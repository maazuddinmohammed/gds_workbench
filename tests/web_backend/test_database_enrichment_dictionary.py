"""Model-local enrichment edit/read/export round trips on disposable PostgreSQL."""

# pyright: reportPrivateUsage=false
from io import BytesIO
from typing import Any, cast
from uuid import uuid4

import httpx2
import pytest
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata_enrichment.dictionary import (
    DatabaseEnrichmentDictionaryService,
)
from gds_workbench_api.features.metadata_enrichment.review import (
    DatabaseEnrichmentReviewService,
)
from gds_workbench_api.features.metadata_enrichment.workbook import (
    DATA_DICTIONARY_COLUMNS,
    TECHNICAL_DICTIONARY_COLUMNS,
)
from gds_workbench_api.main import create_app
from openpyxl import load_workbook

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_profiling_persistence import _seed_attributes
from tests.mcp.test_database_workflow_run_lifecycle import seed_workflow_context


@pytest.mark.asyncio
async def test_edit_read_export_and_model_isolation(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    context = seed_workflow_context(fixture)
    object_id, attribute_id = _seed_attributes(fixture, context)[0]
    with fixture.connect_owner() as connection:
        before_object = connection.execute(
            "SELECT * FROM core.object WHERE object_id=%s", (object_id,)
        ).fetchone()
        before_attribute = connection.execute(
            "SELECT * FROM core.attribute WHERE attribute_id=%s", (attribute_id,)
        ).fetchone()
        other_model = require_row(
            connection.execute(
                "INSERT INTO model.model(tenant_id,model_name) VALUES(%s,%s) RETURNING model_id",
                (context.tenant_id, f"Isolated {uuid4().hex}"),
            ).fetchone()
        )["model_id"]
        connection.execute(
            "INSERT INTO model.model_input_scope(model_id,object_id) VALUES(%s,%s)",
            (other_model, object_id),
        )
        connection.execute(
            "INSERT INTO workflow.attribute_profile(model_id,object_id,attribute_id,source_context_digest,row_count,non_null_count,null_count,blank_count,distinct_count) VALUES(%s,%s,%s,%s,10,10,0,0,10)",
            (context.model_id, object_id, attribute_id, "a" * 64),
        )
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=2, pool_timeout_seconds=5
    )
    identity = IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=context.entra_tenant_id,
        local_principal_object_id=context.entra_object_id,
    )
    dictionary_service = DatabaseEnrichmentDictionaryService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"fixture-enrichment-key-32-bytes!!",
        enrichment=True,
    )
    app = create_app(
        identity_provider=identity,
        enrichment_dictionary_service=dictionary_service,
        enrichment_review_service=DatabaseEnrichmentReviewService(database=database),
    )
    await database.open()
    try:
        await dictionary_service.read_input_scope_object(
            identity.request_principal(None),
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            object_id=object_id,
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://fixture.invalid"
        ) as client:
            base = f"/api/v1/tenants/{context.tenant_id}/models/{context.model_id}/metadata-enrichment"
            initial = await client.get(f"{base}/objects/{object_id}")
            assert initial.status_code == 200
            assert initial.json()["object_description"] is None
            for record_type in ("object", "attribute"):
                detail = (await client.get(f"{base}/objects/{object_id}")).json()
                record = detail if record_type == "object" else detail["attributes"][0]
                record_id = object_id if record_type == "object" else attribute_id
                edit: dict[str, Any] = {
                    "record_id": record_id,
                    "expected_revision": record["review_revision"],
                    "description": "=Literal description",
                }
                if record_type == "attribute":
                    edit.update(
                        attribute_inferred_data_type="BIGINT",
                        is_natural_key=True,
                        is_primary_key=True,
                        is_nullable=False,
                        is_pii=None,
                    )
                body: dict[str, Any] = {
                    "expected_model_revision": context.model_revision,
                    "record_type": record_type,
                    "action": "edit",
                    "records": [edit],
                }
                headers = {"Idempotency-Key": str(uuid4())}
                saved = await client.post(f"{base}/review", json=body, headers=headers)
                assert saved.status_code == 200
                assert (
                    await client.post(f"{base}/review", json=body, headers=headers)
                ).json() == saved.json()
                assert (
                    await client.post(
                        f"{base}/review",
                        json=body,
                        headers={"Idempotency-Key": str(uuid4())},
                    )
                ).status_code == 409
            detail = (await client.get(f"{base}/objects/{object_id}")).json()
            attribute = detail["attributes"][0]
            assert attribute["enrichment"] == {
                "is_natural_key": True,
                "is_primary_key": True,
                "is_nullable": False,
                "is_pii": None,
            }
            assert attribute["attribute_inferred_data_type"] == "BIGINT"
            assert attribute["profile"]["null_count"] == 0
            exported = await client.get(f"{base}/export")
            assert exported.status_code == 200
            assert exported.headers["Content-Disposition"].endswith('_Enrichment.xlsx"')
            assert exported.headers["Cache-Control"] == "no-store"
            workbook = load_workbook(BytesIO(exported.content))
            try:
                assert workbook.sheetnames == [
                    "Data Dictionary",
                    "Technical Data Dictionary",
                ]
                data = workbook.worksheets[0]
                technical = workbook.worksheets[1]
                assert tuple(cell.value for cell in data[1]) == DATA_DICTIONARY_COLUMNS
                assert (
                    tuple(cell.value for cell in technical[1])
                    == TECHNICAL_DICTIONARY_COLUMNS
                )
                row = next(
                    cells
                    for cells in data
                    if cells[3].value == attribute["attribute_name"]
                )
                assert tuple(cell.value for cell in row[4:]) == (
                    "=Literal description",
                    "BIGINT",
                    "string",
                    1,
                    True,
                    True,
                    False,
                    None,
                )
                assert row[4].data_type == "s"
                assert all(
                    cast(Any, cell.border).bottom.style == "thin" for cell in row
                )
                profile = next(
                    cells
                    for cells in technical
                    if cells[2].value == attribute["attribute_name"]
                )
                assert tuple(cell.value for cell in profile[5:10]) == (10, 10, 0, 0, 10)
            finally:
                workbook.close()
            # A second Model sees no saved findings or profiling, despite sharing the Object.
            other_base = base.replace(
                f"/models/{context.model_id}/", f"/models/{other_model}/"
            )
            other = await client.get(f"{other_base}/objects/{object_id}")
            assert other.status_code == 200
            assert other.json()["object_description"] is None
            assert all(
                value is None
                for value in other.json()["attributes"][0]["enrichment"].values()
            )
            assert other.json()["attributes"][0]["profile"] is None
            # Parent Model lock protects child editing; SQL rejects stale Model revisions.
            lock_body = {
                "expected_model_revision": context.model_revision,
                "record_type": "object",
                "action": "lock",
                "records": [
                    {
                        "record_id": object_id,
                        "expected_revision": detail["review_revision"],
                    }
                ],
            }
            assert (
                await client.post(
                    f"{base}/review",
                    json=lock_body,
                    headers={"Idempotency-Key": str(uuid4())},
                )
            ).status_code == 200
            locked = (await client.get(f"{base}/objects/{object_id}")).json()
            body["records"][0]["expected_revision"] = locked["attributes"][0][
                "review_revision"
            ]
            assert (
                await client.post(
                    f"{base}/review",
                    json=body,
                    headers={"Idempotency-Key": str(uuid4())},
                )
            ).status_code == 409
            body["expected_model_revision"] += 1
            assert (
                await client.post(
                    f"{base}/review",
                    json=body,
                    headers={"Idempotency-Key": str(uuid4())},
                )
            ).status_code == 409
            body["records"][0]["is_pii"] = "false"
            assert (
                await client.post(
                    f"{base}/review",
                    json=body,
                    headers={"Idempotency-Key": str(uuid4())},
                )
            ).status_code == 422
            with fixture.connect_owner() as connection:
                connection.execute(
                    "SELECT security.release_tenant_lock(%s,%s,'user',%s)",
                    (
                        context.entra_tenant_id,
                        context.entra_object_id,
                        context.tenant_id,
                    ),
                )
            body["records"][0]["is_pii"] = False
            assert (
                await client.post(
                    f"{base}/review",
                    json=body,
                    headers={"Idempotency-Key": str(uuid4())},
                )
            ).status_code in (403, 409)
    finally:
        await database.close()
    with fixture.connect_owner() as connection:
        assert (
            connection.execute(
                "SELECT * FROM core.object WHERE object_id=%s", (object_id,)
            ).fetchone()
            == before_object
        )
        assert (
            connection.execute(
                "SELECT * FROM core.attribute WHERE attribute_id=%s", (attribute_id,)
            ).fetchone()
            == before_attribute
        )
