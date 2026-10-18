# pyright: reportPrivateUsage=false
"""Context read SQL resolves global types and keeps Project UUID ownership exact."""

from typing import Any
from uuid import uuid4

import httpx2
import pytest
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.context import DatabaseContextService
from gds_workbench_api.features.context.contracts import (
    ContextGroupFilters,
    ContextRecordFilters,
    ContextRecordNotFoundError,
)
from gds_workbench_api.main import create_app

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_project_change_set_round_trip import (
    StaticIdentityProvider,
    _seed_project_foundation,
)


@pytest.mark.parametrize(
    "source_reference", [None, "Source handbook section 4", "é" * 500, "é" * 501]
)
async def test_context_reads_are_project_scoped_and_bounded(
    web_postgres_database: DisposablePostgres,
    source_reference: str | None,
) -> None:
    fixture = web_postgres_database
    project_id, tenant_id = _seed_project_foundation(
        fixture, code_prefix=f"CONTEXT_READ_{uuid4().hex}"
    )
    record_id = uuid4()
    with fixture.connect_owner() as connection:
        context_type = connection.execute(
            "SELECT context_type_id FROM reference.context_type WHERE name='Source Information'"
        ).fetchone()
        assert context_type is not None
        group = connection.execute(
            "INSERT INTO project.context_group (project_id,context_type_id,name,description) "
            "VALUES (%s,%s,'Customer source','Source interpretation') RETURNING context_group_id",
            (project_id, context_type["context_type_id"]),
        ).fetchone()
        assert group is not None
        connection.execute(
            "INSERT INTO project.context_record(context_record_id,project_id,context_group_id,"
            "context_text,source_reference) VALUES (%s,%s,%s,%s,%s)",
            (
                record_id,
                project_id,
                group["context_group_id"],
                "Customer identifiers remain stable. " + "x" * 600,
                source_reference,
            ),
        )
        other = connection.execute(
            "INSERT INTO project.project(tenant_id,project_name) "
            "VALUES (%s,%s) RETURNING project_id",
            (tenant_id, f"Other Context {uuid4().hex}"),
        ).fetchone()
        assert other is not None
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    principal = StaticIdentityProvider().request_principal(None)
    reads = DatabaseContextService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    await database.open()
    try:
        types = await reads.list_types(principal, tenant_id=tenant_id, project_id=project_id)
        assert len(types.items) >= 12
        groups = await reads.list_groups(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            filters=ContextGroupFilters(context_type_id=context_type["context_type_id"]),
            page_size=50,
            cursor=None,
        )
        assert len(groups.items) == 1 and groups.items[0].record_count == 1
        records = await reads.list_records(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            filters=ContextRecordFilters(
                group_id=group["context_group_id"], text_search="identifiers"
            ),
            page_size=50,
            cursor=None,
        )
        assert records.items[0].context_record_id == str(record_id)
        assert records.items[0].text_truncated and len(records.items[0].context_text_preview) == 500
        assert records.items[0].source_reference_preview == (
            source_reference[:500] if source_reference is not None else None
        )
        assert records.items[0].source_reference_truncated == (
            source_reference is not None and len(source_reference) > 500
        )
        detail = await reads.read_record(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            context_record_id=str(record_id),
        )
        assert detail.group.context_type.context_type_name == "Source Information"
        assert detail.source_reference == source_reference
        assert detail.source_reference_preview == records.items[0].source_reference_preview
        assert detail.source_reference_truncated == records.items[0].source_reference_truncated
        assert len(detail.context_text) > 500
        with pytest.raises(ContextRecordNotFoundError):
            await reads.read_record(
                principal,
                tenant_id=tenant_id,
                project_id=other["project_id"],
                context_record_id=str(record_id),
            )
    finally:
        await database.close()


async def test_context_source_system_api_lists_active_global_systems_with_project_access(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    prefix = f"CONTEXT_SYSTEMS_{uuid4().hex}"
    project_id, tenant_id = _seed_project_foundation(fixture, code_prefix=prefix)
    other_project_id, _ = _seed_project_foundation(
        fixture, code_prefix=f"CONTEXT_OTHER_{uuid4().hex}"
    )
    with fixture.connect_owner() as connection:
        system_type = connection.execute(
            "INSERT INTO reference.system_type(system_type_code,system_type_name,is_active) "
            "VALUES (%s,'Descriptive source type',FALSE) RETURNING system_type_id",
            (prefix,),
        ).fetchone()
        assert system_type is not None
        source_ids: list[int] = []
        for suffix, active in (("Z", True), ("a", True), ("Inactive", False)):
            source = connection.execute(
                "INSERT INTO core.system(system_code,system_name,system_type_id,is_active) "
                "VALUES (%s,%s,%s,%s) RETURNING system_id",
                (
                    f"{prefix}_{suffix}",
                    f"Descriptive source {suffix}",
                    system_type["system_type_id"],
                    active,
                ),
            ).fetchone()
            assert source is not None
            source_ids.append(source["system_id"])
        # Descriptive Context sources need no Tenant Connection. Inactive types
        # also do not narrow the active-System rule used by Context authoring.
        assert (
            connection.execute(
                "SELECT connection_id FROM core.connection WHERE system_id=ANY(%s)",
                (source_ids,),
            ).fetchall()
            == []
        )
        expected = connection.execute(
            "SELECT system_id,system_code,system_name FROM core.system WHERE is_active "
            "ORDER BY lower(btrim(system_code)),system_id"
        ).fetchall()
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    principal = StaticIdentityProvider().request_principal(None)
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=principal.entra_tenant_id,
            local_principal_object_id=principal.entra_object_id,
        ),
        context_service=DatabaseContextService(
            database=database,
            authorizer=AuthorizationService(),
            cursor_signing_key=b"development-only-key-32-bytes-long",
        ),
    )
    await database.open()
    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://fixture.invalid"
        ) as client:
            path = f"/api/v1/tenants/{tenant_id}/projects/{project_id}/context/source-systems"
            items: list[dict[str, Any]] = []
            cursor = None
            for _ in range(len(expected) + 1):
                parameters = {"page_size": "2"}
                if cursor is not None:
                    parameters["cursor"] = cursor
                response = await client.get(path, params=parameters)
                assert response.status_code == 200
                page = response.json()
                assert set(page) == {"items", "next_cursor"}
                assert len(page["items"]) <= 2
                items.extend(page["items"])
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            else:
                pytest.fail("Context source System pagination did not terminate")
            assert items == expected
            returned_ids = {item["system_id"] for item in items}
            assert set(source_ids[:2]) <= returned_ids
            assert source_ids[2] not in returned_ids
            wrong_project = path.replace(f"projects/{project_id}", f"projects/{other_project_id}")
            assert (await client.get(wrong_project)).status_code == 404
            with fixture.connect_owner() as connection:
                connection.execute(
                    "UPDATE project.project SET is_active=FALSE WHERE project_id=%s",
                    (project_id,),
                )
            assert (await client.get(path)).status_code == 404
            with fixture.connect_owner() as connection:
                connection.execute(
                    "UPDATE security.tenant_principal_access SET is_active=FALSE "
                    "WHERE tenant_id=%s",
                    (tenant_id,),
                )
            denied = await client.get(path)
            assert denied.status_code == 404
            assert denied.json()["error"]["code"] == "tenant_not_found"
    finally:
        await database.close()
